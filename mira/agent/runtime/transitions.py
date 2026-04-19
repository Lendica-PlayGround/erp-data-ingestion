"""Application-side state transition rules (PRD §6.1). DB triggers mirror these for defense in depth."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent.models.mapping_contract import MappingContract
from agent.models.onboarding import OnboardingState

LEGAL_EDGES: dict[str, set[str]] = {
    "intake": {"research", "failed"},
    "research": {"map", "failed"},
    "map": {"awaiting_approval", "failed"},
    "awaiting_approval": {"code", "failed"},
    "code": {"dry_run", "failed"},
    "dry_run": {"initial_sync", "failed"},
    "initial_sync": {"scheduled", "failed"},
    "scheduled": {"failed"},
    "failed": set(),
}


def _mapping_contract_valid(doc: dict[str, Any]) -> bool:
    raw = doc.get("mapping_contract")
    if raw is None:
        return False
    schema_path = (
        Path(__file__).resolve().parents[2] / "schemas" / "mapping_contract" / "v1.schema.json"
    )
    try:
        MappingContract.model_validate(raw)
    except Exception:
        return False
    if schema_path.is_file():
        try:
            import jsonschema

            with schema_path.open(encoding="utf-8") as f:
                schema = json.load(f)
            jsonschema.validate(raw, schema)
        except ImportError:
            pass
        except jsonschema.ValidationError:
            return False
    return True


def transition_allowed(current: OnboardingState, new_state: str) -> tuple[bool, str]:
    if new_state == current.state:
        return True, "noop"
    allowed = LEGAL_EDGES.get(current.state, set())
    if new_state not in allowed:
        return False, f"Illegal edge {current.state} -> {new_state}"
    doc = current.model_dump(mode="json")
    if current.state == "intake" and new_state == "research":
        sys = doc.get("source", {}).get("system")
        if sys in (None, "unknown"):
            return False, "intake -> research requires source.system != unknown"
    if current.state == "map" and new_state == "awaiting_approval":
        if not _mapping_contract_valid(doc):
            return False, "map -> awaiting_approval requires valid mapping_contract"
    if current.state == "awaiting_approval" and new_state == "code":
        a = doc.get("approval") or {}
        if not a.get("customer_confirmed_at") or not a.get("fde_confirmed_at"):
            return False, "awaiting_approval -> code requires both approvals"
    if current.state == "code" and new_state == "dry_run":
        pr = (doc.get("phase3") or {}).get("pr_url")
        if not pr:
            return False, "code -> dry_run requires phase3.pr_url from open_pr"
    if current.state == "dry_run" and new_state == "initial_sync":
        errs = (doc.get("phase3") or {}).get("dry_run_errors") or []
        if errs:
            return False, "dry_run -> initial_sync requires zero dry_run_errors"
    if current.state == "initial_sync" and new_state == "scheduled":
        manifest = (doc.get("phase3") or {}).get("initial_sync_manifest")
        if not manifest:
            return False, "initial_sync -> scheduled requires phase3.initial_sync_manifest"
    return True, "ok"


def assert_transition(current: OnboardingState, new_state: str) -> None:
    ok, msg = transition_allowed(current, new_state)
    if not ok:
        raise ValueError(msg)
