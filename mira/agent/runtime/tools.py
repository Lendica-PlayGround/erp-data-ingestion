"""LangChain tools backing Mira skills (PRD §2.5)."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID

import httpx
import jwt
from langchain_core.tools import StructuredTool

from agent.models.mapping_contract import MappingContract
from agent.models.onboarding import ColumnDescription, OnboardingState, TableDescription
from agent.runtime.context import RunContext
from agent.runtime.transitions import assert_transition, transition_allowed


def _uuid(run_id: str) -> UUID:
    return UUID(run_id.strip())


def _run(ctx: RunContext, run_id: str) -> OnboardingState:
    rid = _uuid(run_id)
    if rid != ctx.run_id:
        raise ValueError("run_id does not match bound session")
    st = ctx.store.get(rid)
    if st is None:
        raise ValueError("Unknown run_id — create run first")
    return st


def _state_store_impl(
    ctx: RunContext,
    operation: Literal["get", "patch"],
    run_id: str,
    patch_json: str | None = None,
    new_state: str | None = None,
) -> str:
    rid = _uuid(run_id)
    if rid != ctx.run_id:
        return json.dumps({"ok": False, "error": "run_id mismatch"})
    if operation == "get":
        st = ctx.store.get(rid)
        if st is None:
            return json.dumps({"ok": False, "error": "not found"})
        return json.dumps({"ok": True, "document": st.model_dump(mode="json")}, default=str)

    if not patch_json:
        return json.dumps({"ok": False, "error": "patch requires patch_json"})
    patch = json.loads(patch_json)
    current = ctx.store.get(rid)
    if current is None:
        return json.dumps({"ok": False, "error": "not found"})
    candidate = current.model_copy(deep=True)
    candidate.apply_patch(patch)
    if new_state is not None:
        candidate.state = new_state  # type: ignore[assignment]
    if candidate.state != current.state:
        assert_transition(current, candidate.state)
    ctx.store.put(candidate)
    return json.dumps({"ok": True, "document": candidate.model_dump(mode="json")}, default=str)


def _discover_source_impl(
    ctx: RunContext,
    run_id: str,
    system: str,
    access_method: str,
    tables_csv: str,
) -> str:
    _run(ctx, run_id)
    tables = [t.strip() for t in tables_csv.split(",") if t.strip()]
    patch: dict[str, Any] = {
        "source": {"system": system, "access_method": access_method},
        "tables_in_scope": tables,
    }
    ctx.store.patch(ctx.run_id, patch, "discover_source")
    fresh = ctx.store.get(ctx.run_id)
    if fresh is None:
        return json.dumps({"ok": False})
    ok, msg = transition_allowed(fresh, "research")
    advanced = False
    if ok and system != "unknown":
        assert_transition(fresh, "research")
        ctx.store.patch(ctx.run_id, {"state": "research"}, "discover_source_advance")
        advanced = True
    return json.dumps({"ok": True, "advanced_to_research": advanced, "note": msg})


def _validate_credentials_impl(
    ctx: RunContext, run_id: str, vault_ref: str, probe_ok: bool
) -> str:
    _ = vault_ref
    _run(ctx, run_id)
    status = "validated" if probe_ok else "failed"
    ctx.store.patch(ctx.run_id, {"source": {"auth_status": status}}, "validate_credentials")
    return json.dumps({"ok": True, "auth_status": status})


def _research_vendor_impl(ctx: RunContext, run_id: str, query: str) -> str:
    _run(ctx, run_id)
    key = os.getenv("TAVILY_API_KEY")
    if not key:
        ctx.store.patch(
            ctx.run_id,
            {
                "blockers": [
                    {
                        "code": "research_unavailable",
                        "message": "TAVILY_API_KEY not set",
                        "needs": "research",
                    }
                ]
            },
            "research_vendor",
        )
        return json.dumps({"ok": False, "error": "no_tavily"})
    try:
        r = httpx.post(
            "https://api.tavily.com/search",
            json={"api_key": key, "query": query, "search_depth": "basic"},
            timeout=30.0,
        )
        r.raise_for_status()
        results = r.json().get("results") or []
        uris = [str(x.get("url")) for x in results[:5] if x.get("url")]
    except Exception as e:
        return json.dumps({"ok": False, "error": str(e)})
    artifacts = [
        {
            "kind": "api_doc_url",
            "uri": u,
            "ingested_at": datetime.now(timezone.utc).isoformat(),
        }
        for u in uris
    ]
    ctx.store.patch(ctx.run_id, {"artifacts_collected": artifacts}, "research_vendor")
    return json.dumps({"ok": True, "urls": uris})


def _profile_table_impl(
    ctx: RunContext, run_id: str, table_name: str, table_json: str, columns_json: str
) -> str:
    _run(ctx, run_id)
    table = TableDescription.model_validate(json.loads(table_json))
    columns_raw = json.loads(columns_json)
    st = ctx.store.get(ctx.run_id)
    if st is None:
        return json.dumps({"ok": False})
    tables = [t for t in st.table_descriptions if t.table_name != table_name]
    tables.append(table)
    cols = [c for c in st.column_descriptions if c.table_name != table_name]
    cols.extend(ColumnDescription.model_validate(c) for c in columns_raw)
    ctx.store.patch(
        ctx.run_id,
        {"table_descriptions": tables, "column_descriptions": cols},
        "profile_table",
    )
    return json.dumps({"ok": True})


def _draft_mapping_impl(ctx: RunContext, run_id: str, source_system: str, company_id: str) -> str:
    st = _run(ctx, run_id)
    mapping_version = f"{source_system}.bundle.v0.0.1"
    contract: dict[str, Any] = {
        "mapping_version": mapping_version,
        "midlayer_schema_version": "v1",
        "company_id": company_id,
        "source_profile": st.source.model_dump(mode="json"),
        "objects": [
            {
                "midlayer_table": "invoice",
                "source_entity": f"{source_system}.invoice",
                "object_confidence": 0.9,
                "unmapped_source_fields": [],
                "fields": [
                    {
                        "midlayer_field": "external_id",
                        "source_field": "id",
                        "confidence": 0.99,
                        "transforms": [{"op": "identity"}],
                    },
                    {
                        "midlayer_field": "total_amount",
                        "source_field": "amount_due",
                        "confidence": 0.95,
                        "transforms": [{"op": "divide", "by": 100, "reason": "cents to major"}],
                    },
                ],
            },
            {
                "midlayer_table": "customer",
                "source_entity": f"{source_system}.customer",
                "object_confidence": 0.85,
                "unmapped_source_fields": [],
                "fields": [
                    {
                        "midlayer_field": "external_id",
                        "source_field": "id",
                        "confidence": 0.99,
                        "transforms": [{"op": "identity"}],
                    }
                ],
            },
            {
                "midlayer_table": "contact",
                "source_entity": f"{source_system}.contact",
                "object_confidence": 0.8,
                "unmapped_source_fields": [],
                "fields": [
                    {
                        "midlayer_field": "external_id",
                        "source_field": "id",
                        "confidence": 0.99,
                        "transforms": [{"op": "identity"}],
                    }
                ],
            },
        ],
        "sync_strategy": {
            "initial": "full_historical",
            "delta": {"mode": "cursor", "cursor_field": "updated", "cadence": "daily"},
        },
        "validation_requirements": [
            "row_count_matches_source",
            "no_null_in_required_fields",
            "currency_present_when_amount_present",
        ],
    }
    MappingContract.model_validate(contract)
    ctx.store.patch(ctx.run_id, {"mapping_contract": contract}, "draft_mapping")
    return json.dumps({"ok": True, "mapping_version": mapping_version})


def _render_irr_impl(ctx: RunContext, run_id: str) -> str:
    st = _run(ctx, run_id)
    mc = st.mapping_contract or {}
    lines = [
        f"Implementation Readiness Review — {st.company_id} — {st.source.system}",
        "",
        f"Objects: {', '.join(st.tables_in_scope) or 'n/a'}",
        f"Mapping version: {mc.get('mapping_version', 'n/a')}",
        "",
        "Approval required:",
        " [ ] Customer confirms business meaning",
        " [ ] FDE confirms implementation plan",
    ]
    body = "\n".join(lines)
    ctx.store.patch(ctx.run_id, {"phase3": {"irr_markdown": body}}, "render_irr")
    ctx.emit(body)
    return json.dumps({"ok": True, "irr_markdown": body})


def _await_approvals_impl(ctx: RunContext, run_id: str) -> str:
    st = _run(ctx, run_id)
    a = st.approval
    ready = bool(a.customer_confirmed_at and a.fde_confirmed_at)
    return json.dumps(
        {
            "ok": ready,
            "customer": a.customer_confirmed_at is not None,
            "fde": a.fde_confirmed_at is not None,
        },
        default=str,
    )


def _lock_contract_impl(ctx: RunContext, run_id: str) -> str:
    _run(ctx, run_id)
    ts = datetime.now(timezone.utc).isoformat()
    ctx.store.patch(ctx.run_id, {"phase3": {"contract_locked_at": ts}}, "lock_contract")
    return json.dumps({"ok": True, "contract_locked_at": ts})


def _generate_connector_impl(ctx: RunContext, run_id: str) -> str:
    st = _run(ctx, run_id)
    src = st.source.system
    base = ctx.workspace_root / "connectors" / st.company_id / src
    base.mkdir(parents=True, exist_ok=True)
    (base / "connector_config.yaml").write_text(
        f"company_id: {st.company_id}\nsource: {src}\nmapping_version: "
        f"{(st.mapping_contract or {}).get('mapping_version', 'unknown')}\n",
        encoding="utf-8",
    )
    (base / "source_adapter.py").write_text(
        "from framework.connector_interface import DataConnector\n\n"
        "class SourceAdapter(DataConnector):\n"
        "    def extract_initial(self, limit: int | None = None):\n"
        "        raise NotImplementedError\n"
        "    def extract_delta(self, cursor: str | None):\n"
        "        raise NotImplementedError\n",
        encoding="utf-8",
    )
    (base / "transform_invoice.py").write_text("# transforms\n", encoding="utf-8")
    (base / "transform_customer.py").write_text("# transforms\n", encoding="utf-8")
    (base / "transform_contact.py").write_text("# transforms\n", encoding="utf-8")
    (base / "sync_runner.py").write_text(
        "def main() -> None:\n    print('sync_runner stub')\n",
        encoding="utf-8",
    )
    (base / "validation.py").write_text("# validation\n", encoding="utf-8")
    (base / "README.md").write_text("# Generated connector\n", encoding="utf-8")
    return json.dumps({"ok": True, "path": str(base)})


def _generate_tests_impl(ctx: RunContext, run_id: str) -> str:
    st = _run(ctx, run_id)
    base = ctx.workspace_root / "connectors" / st.company_id / st.source.system / "tests"
    (base / "fixtures").mkdir(parents=True, exist_ok=True)
    (base / "test_transforms.py").write_text("def test_stub():\n    assert True\n", encoding="utf-8")
    (base / "test_schema_compliance.py").write_text("def test_stub():\n    assert True\n", encoding="utf-8")
    (base / "test_delta_cursor.py").write_text("def test_stub():\n    assert True\n", encoding="utf-8")
    return json.dumps({"ok": True, "path": str(base)})


def _open_pr_impl(ctx: RunContext, run_id: str) -> str:
    _run(ctx, run_id)
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        url = "https://example.invalid/mira-placeholder-pr"
        ctx.store.patch(ctx.run_id, {"phase3": {"pr_url": url}}, "open_pr")
        return json.dumps({"ok": True, "pr_url": url, "note": "placeholder_no_token"})
    repo = os.getenv("GITHUB_REPOSITORY", "")
    if not repo:
        return json.dumps({"ok": False, "error": "GITHUB_REPOSITORY not set"})
    return json.dumps({"ok": False, "error": "GitHub PR creation not implemented in MVP stub"})


def _run_dry_sync_impl(ctx: RunContext, run_id: str) -> str:
    _run(ctx, run_id)
    ctx.store.patch(
        ctx.run_id,
        {"phase3": {"dry_run": {"rows": 0}, "dry_run_errors": []}},
        "run_dry_sync",
    )
    return json.dumps({"ok": True})


def _run_initial_sync_impl(ctx: RunContext, run_id: str) -> str:
    _run(ctx, run_id)
    manifest = {"generated_at": datetime.now(timezone.utc).isoformat(), "tables": []}
    ctx.store.patch(ctx.run_id, {"phase3": {"initial_sync_manifest": manifest}}, "run_initial_sync")
    return json.dumps({"ok": True, "manifest": manifest})


def _schedule_delta_sync_impl(ctx: RunContext, run_id: str) -> str:
    _run(ctx, run_id)
    dag_path = ctx.workspace_root / "dags" / f"mira_{ctx.run_id}_delta.py"
    dag_path.parent.mkdir(parents=True, exist_ok=True)
    dag_path.write_text(
        "from airflow import DAG\nfrom datetime import datetime\n"
        f"DAG(dag_id='mira_{ctx.run_id}', start_date=datetime(2026,1,1), schedule_interval='@daily')\n",
        encoding="utf-8",
    )
    ctx.store.patch(ctx.run_id, {"phase3": {"dag_path": str(dag_path)}}, "schedule_delta_sync")
    return json.dumps({"ok": True, "dag_path": str(dag_path)})


def _issue_dashboard_jwt_impl(ctx: RunContext, run_id: str) -> str:
    st = _run(ctx, run_id)
    secret = os.getenv("MIRA_JWT_SECRET", "dev-insecure-secret")
    token = jwt.encode(
        {"company_id": st.company_id, "run_id": str(st.run_id)},
        secret,
        algorithm="HS256",
    )
    base = os.getenv("MIRA_DASHBOARD_BASE_URL", "http://localhost:8090/dashboard")
    url = f"{base}?token={token}"
    ctx.store.patch(ctx.run_id, {"phase3": {"dashboard_url": url}}, "issue_dashboard_jwt")
    ctx.emit(url)
    return json.dumps({"ok": True, "dashboard_url": url})


def _escalate_to_fde_impl(ctx: RunContext, run_id: str, code: str, message: str) -> str:
    _run(ctx, run_id)
    payload = f"@FDE blocker[{code}]: {message} (run {run_id})"
    ctx.emit(payload)
    current = ctx.store.get(ctx.run_id)
    if current is None:
        return json.dumps({"ok": False})
    assert_transition(current, "failed")
    ctx.store.patch(
        ctx.run_id,
        {
            "blockers": [{"code": code, "message": message, "needs": "fde_input"}],
            "state": "failed",
        },
        "escalate_to_fde",
    )
    return json.dumps({"ok": True})


def build_mira_tools(ctx: RunContext) -> list[StructuredTool]:
    """Bind tools to a run context (nested defs so LangChain can introspect signatures)."""

    def state_store(
        operation: Literal["get", "patch"],
        run_id: str,
        patch_json: str | None = None,
        new_state: str | None = None,
    ) -> str:
        return _state_store_impl(ctx, operation, run_id, patch_json, new_state)

    def discover_source(run_id: str, system: str, access_method: str, tables_csv: str) -> str:
        return _discover_source_impl(ctx, run_id, system, access_method, tables_csv)

    def validate_credentials(run_id: str, vault_ref: str, probe_ok: bool) -> str:
        return _validate_credentials_impl(ctx, run_id, vault_ref, probe_ok)

    def research_vendor(run_id: str, query: str) -> str:
        return _research_vendor_impl(ctx, run_id, query)

    def profile_table(run_id: str, table_name: str, table_json: str, columns_json: str) -> str:
        return _profile_table_impl(ctx, run_id, table_name, table_json, columns_json)

    def draft_mapping(run_id: str, source_system: str, company_id: str) -> str:
        return _draft_mapping_impl(ctx, run_id, source_system, company_id)

    def render_irr(run_id: str) -> str:
        return _render_irr_impl(ctx, run_id)

    def await_approvals(run_id: str) -> str:
        return _await_approvals_impl(ctx, run_id)

    def lock_contract(run_id: str) -> str:
        return _lock_contract_impl(ctx, run_id)

    def generate_connector(run_id: str) -> str:
        return _generate_connector_impl(ctx, run_id)

    def generate_tests(run_id: str) -> str:
        return _generate_tests_impl(ctx, run_id)

    def open_pr(run_id: str) -> str:
        return _open_pr_impl(ctx, run_id)

    def run_dry_sync(run_id: str) -> str:
        return _run_dry_sync_impl(ctx, run_id)

    def run_initial_sync(run_id: str) -> str:
        return _run_initial_sync_impl(ctx, run_id)

    def schedule_delta_sync(run_id: str) -> str:
        return _schedule_delta_sync_impl(ctx, run_id)

    def issue_dashboard_jwt(run_id: str) -> str:
        return _issue_dashboard_jwt_impl(ctx, run_id)

    def escalate_to_fde(run_id: str, code: str, message: str) -> str:
        return _escalate_to_fde_impl(ctx, run_id, code, message)

    specs: list[tuple[str, str, Any]] = [
        ("state_store", "Read or patch the onboarding document.", state_store),
        ("discover_source", "Intake fields; may advance intake→research.", discover_source),
        ("validate_credentials", "Set auth_status after vault + probe.", validate_credentials),
        ("research_vendor", "Vendor doc search via Tavily when configured.", research_vendor),
        ("profile_table", "Merge table + column profiling JSON.", profile_table),
        ("draft_mapping", "Draft minimal mapping_contract for MVP tables.", draft_mapping),
        ("render_irr", "Render Implementation Readiness Review markdown.", render_irr),
        ("await_approvals", "Check customer + FDE approval timestamps.", await_approvals),
        ("lock_contract", "Phase 3.1 lock timestamp in phase3.", lock_contract),
        ("generate_connector", "Write connector skeleton to workspace.", generate_connector),
        ("generate_tests", "Write stub pytest files.", generate_tests),
        ("open_pr", "Record pr_url (placeholder without GITHUB_TOKEN).", open_pr),
        ("run_dry_sync", "Record dry-run summary for gating.", run_dry_sync),
        ("run_initial_sync", "Record initial_sync_manifest.", run_initial_sync),
        ("schedule_delta_sync", "Write stub Airflow DAG under workspace/dags.", schedule_delta_sync),
        ("issue_dashboard_jwt", "Mint dashboard JWT + URL.", issue_dashboard_jwt),
        ("escalate_to_fde", "Notify FDE; transition to failed.", escalate_to_fde),
    ]
    return [StructuredTool.from_function(fn, name=name, description=desc) for name, desc, fn in specs]
