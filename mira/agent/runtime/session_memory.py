from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID

from agent.models.onboarding import (
    ConversationTurn,
    OnboardingState,
    RecommendedPlan,
    ResearchSummary,
    SourceSystem,
    StakeholderSummary,
)
from agent.runtime.transitions import assert_transition, transition_allowed
from agent.stores.base import StateStore

_SOURCE_PATTERNS: dict[str, tuple[str, ...]] = {
    "epicor": ("epicor",),
    "stripe": ("stripe",),
    "invoiced": ("invoiced", "invoiced.com"),
    "google_sheets": ("google sheets", "gsheets", "spreadsheet"),
}

_ACCESS_PATTERNS: dict[str, tuple[str, ...]] = {
    "api_key": ("api", "rest", "token", "api key"),
    "oauth": ("oauth",),
    "sftp": ("sftp",),
    "db_dump": ("database dump", "db dump", "sql dump"),
    "shared_drive": ("shared drive", "drive folder"),
    "csv_export": ("csv", "export", "flat file", "spreadsheet export"),
}

_DEPLOYMENT_PATTERNS = ("on-prem", "on prem", "cloud", "hosted", "self-hosted")
_CREDENTIAL_PATTERNS = [
    re.compile(r"\bsk_(?:test|live)_[A-Za-z0-9]{12,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z\-_]{20,}\b"),
    re.compile(r"\b[A-Za-z0-9_\-]{24,}\.[A-Za-z0-9_\-]{6,}\.[A-Za-z0-9_\-]{20,}\b"),
    re.compile(r"(?i)\b(?:api[_ -]?key|token|secret|password)\s*[:=]\s*[A-Za-z0-9_\-]{12,}\b"),
]
_REDACTION_REPLACEMENT = "[redacted credential]"

_HEURISTIC_RESEARCH: dict[str, dict[str, Any]] = {
    "epicor": {
        "summary": (
            "Epicor onboarding usually starts by determining whether the client uses REST "
            "services, BAQ exports, or recurring flat-file extracts. Success depends on "
            "identifying where invoice, customer, and contact data live and whether cloud "
            "or on-prem deployment limits direct API access."
        ),
        "likely_access_paths": ["api_key", "csv_export", "shared_drive", "sftp"],
        "known_quirks": [
            "Epicor deployments vary widely across cloud vs on-prem and customization level.",
            "Invoice and customer objects may come from BAQs or exported reports rather than a single clean API.",
            "Access often depends on an internal Epicor admin or partner team."
        ],
        "open_questions": [
            "Is this Epicor cloud or on-prem?",
            "Do you have REST/API access, scheduled exports, or only manual reports?",
            "Which object matters first: invoice, customer, or contact?"
        ],
        "doc_urls": [],
        "note": "Using built-in Epicor heuristics because live web research may be unavailable.",
    },
    "stripe": {
        "summary": (
            "Stripe usually supports direct API ingestion for invoices, customers, and contacts "
            "with predictable pagination and update timestamps."
        ),
        "likely_access_paths": ["api_key"],
        "known_quirks": [
            "Amounts are commonly returned in minor currency units.",
            "Customers and invoices may need expansion or follow-up fetches for related objects."
        ],
        "open_questions": [
            "Do you have a restricted read-only API key?",
            "Do you need historical backfill or only forward sync?"
        ],
        "doc_urls": ["https://docs.stripe.com/api"],
        "note": "Using built-in Stripe heuristics.",
    },
}


def infer_source_system(text: str) -> str | None:
    low = text.lower()
    for system, patterns in _SOURCE_PATTERNS.items():
        if any(pattern in low for pattern in patterns):
            return system
    return None


def infer_access_method(text: str) -> str | None:
    low = text.lower()
    for method, patterns in _ACCESS_PATTERNS.items():
        if any(pattern in low for pattern in patterns):
            return method
    return None


def text_contains_credential(text: str) -> bool:
    return any(pattern.search(text) for pattern in _CREDENTIAL_PATTERNS)


def redact_credentials(text: str) -> str:
    redacted = text
    for pattern in _CREDENTIAL_PATTERNS:
        redacted = pattern.sub(_REDACTION_REPLACEMENT, redacted)
    return redacted


def trim_conversation_history(turns: list[ConversationTurn], limit: int = 8) -> list[ConversationTurn]:
    return turns[-limit:]


def append_conversation_turn(
    store: StateStore, run_id: UUID, role: str, text: str, channel: str = "chat"
) -> OnboardingState | None:
    current = store.get(run_id)
    if current is None:
        return None
    updated = current.model_copy(deep=True)
    updated.conversation_history.append(
        ConversationTurn(
            role=role, text=text.strip(), channel=channel, created_at=datetime.now(timezone.utc)
        )
    )
    updated.conversation_history = trim_conversation_history(updated.conversation_history)
    store.put(updated)
    return updated


def maybe_capture_message_facts(store: StateStore, run_id: UUID, message: str) -> OnboardingState | None:
    current = store.get(run_id)
    if current is None:
        return None

    patch: dict[str, Any] = {}
    inferred_system = infer_source_system(message)
    if inferred_system and current.source.system == "unknown":
        patch.setdefault("source", {})["system"] = inferred_system

    inferred_access = infer_access_method(message)
    if inferred_access and current.source.access_method == "unknown":
        patch.setdefault("source", {})["access_method"] = inferred_access

    if patch:
        store.patch(run_id, patch, "message_fact_capture")

    fresh = store.get(run_id)
    if fresh is not None and fresh.state == "intake" and fresh.source.system != "unknown":
        ok, _ = transition_allowed(fresh, "research")
        if ok:
            assert_transition(fresh, "research")
            store.patch(run_id, {"state": "research"}, "message_fact_capture_advance")
            fresh = store.get(run_id)
    if (
        fresh is not None
        and fresh.source.system != "unknown"
        and fresh.research_summary.status == "not_started"
    ):
        research = heuristic_research_for_state(fresh)
        temp = fresh.model_copy(deep=True)
        temp.research_summary = research
        temp.recommended_plan = build_recommended_plan(temp)
        store.patch(
            run_id,
            {
                "research_summary": research.model_dump(mode="json"),
                "recommended_plan": temp.recommended_plan.model_dump(mode="json"),
                "open_questions": research.open_questions,
                "next_question": research.open_questions[0] if research.open_questions else fresh.next_question,
            },
            "message_fact_capture_research_seed",
        )
        fresh = store.get(run_id)
    return fresh


def message_has_onboarding_signal(text: str, has_attachment: bool = False) -> bool:
    if has_attachment:
        return True
    low = text.lower()
    if any(pattern in low for patterns in _SOURCE_PATTERNS.values() for pattern in patterns):
        return True
    if any(pattern in low for patterns in _ACCESS_PATTERNS.values() for pattern in patterns):
        return True
    if any(pattern in low for pattern in _DEPLOYMENT_PATTERNS):
        return True
    return text_contains_credential(text)


def answers_open_question(
    state: OnboardingState,
    text: str,
    *,
    window_messages: int = 8,
    window_seconds: int = 900,
    now: datetime | None = None,
) -> bool:
    if not state.next_question or not text.strip():
        return False
    assistant_index = None
    assistant_turn = None
    for idx in range(len(state.conversation_history) - 1, -1, -1):
        turn = state.conversation_history[idx]
        if turn.role == "assistant":
            assistant_index = idx
            assistant_turn = turn
            break
    if assistant_index is None or assistant_turn is None:
        return False
    messages_since_bot = len(state.conversation_history) - 1 - assistant_index
    if messages_since_bot > window_messages:
        return False
    ref_now = now or datetime.now(timezone.utc)
    age_seconds = (ref_now - assistant_turn.created_at).total_seconds()
    return age_seconds <= window_seconds


def record_telegram_sender_context(
    store: StateStore,
    run_id: UUID,
    *,
    user_id: int | None,
    username: str | None,
    full_name: str,
    role: Literal["customer", "fde", "other"],
) -> OnboardingState | None:
    current = store.get(run_id)
    if current is None:
        return None
    updated = current.model_copy(deep=True)
    matched = False
    for stakeholder in updated.stakeholder_context:
        if stakeholder.telegram_user_id and user_id is not None and stakeholder.telegram_user_id == str(user_id):
            stakeholder.telegram_username = username
            stakeholder.name = stakeholder.name or full_name
            stakeholder.role = role
            matched = True
            break
    if not matched:
        updated.stakeholder_context.append(
            StakeholderSummary(
                name=full_name,
                role=role,
                telegram_username=username,
                telegram_user_id=str(user_id) if user_id is not None else None,
            )
        )
    updated.phase3 = {
        **updated.phase3,
        "telegram_context": {
            "last_sender_name": full_name,
            "last_sender_role": role,
            "last_sender_username": username or "",
            "last_sender_user_id": str(user_id) if user_id is not None else "",
        },
    }
    store.put(updated)
    return updated


def recent_dialogue_messages(state: OnboardingState, limit: int = 6) -> list[tuple[str, str]]:
    messages: list[tuple[str, str]] = []
    for turn in state.conversation_history[-limit:]:
        if turn.role in {"user", "assistant"} and turn.text.strip():
            messages.append((turn.role, redact_credentials(turn.text.strip())))
    return messages


def summarize_state_for_prompt(state: OnboardingState) -> str:
    research = state.research_summary
    plan = state.recommended_plan
    lines = [
        "## Current Run Summary",
        f"- run_id: {state.run_id}",
        f"- company_id: {state.company_id}",
        f"- phase: {state.state}",
        f"- source.system: {state.source.system}",
        f"- source.access_method: {state.source.access_method}",
        f"- source.deployment: {state.source.deployment}",
        f"- tables_in_scope: {', '.join(state.tables_in_scope) if state.tables_in_scope else 'unknown'}",
        f"- project_objective: {state.project_objective or 'unknown'}",
        (
            "- success_criteria: "
            + (", ".join(state.success_criteria) if state.success_criteria else "not captured yet")
        ),
        (
            "- constraints: "
            + (", ".join(state.constraints) if state.constraints else "none captured yet")
        ),
        (
            "- open_questions: "
            + (", ".join(state.open_questions) if state.open_questions else "none recorded")
        ),
        f"- next_question: {state.next_question or 'not set'}",
    ]
    if research.status != "not_started":
        lines.extend(
            [
                f"- research.status: {research.status}",
                f"- research.summary: {research.summary or 'none'}",
                (
                    "- research.likely_access_paths: "
                    + (", ".join(research.likely_access_paths) if research.likely_access_paths else "none")
                ),
            ]
        )
    if plan.summary or plan.steps:
        lines.extend(
            [
                f"- recommended_plan.summary: {plan.summary or 'none'}",
                (
                    "- recommended_plan.steps: "
                    + (" | ".join(plan.steps) if plan.steps else "none")
                ),
            ]
        )
    if state.stakeholder_context:
        stakeholders = ", ".join(
            f"{s.role}:{s.name or s.telegram_username or 'unknown'}" for s in state.stakeholder_context
        )
        lines.append(f"- stakeholders: {stakeholders}")
    telegram_context = state.phase3.get("telegram_context", {}) if isinstance(state.phase3, dict) else {}
    if telegram_context:
        sender_name = telegram_context.get("last_sender_name") or "unknown"
        sender_role = telegram_context.get("last_sender_role") or "unknown"
        sender_username = telegram_context.get("last_sender_username") or "unknown"
        lines.append(f"- last_sender: {sender_role} ({sender_name}, @{sender_username})")
    lines.append(f"- telegram_muted: {state.ui_preferences.telegram.muted}")
    if state.conversation_history:
        recent = " | ".join(
            f"{turn.role}: {redact_credentials(turn.text)}"
            for turn in state.conversation_history[-3:]
            if turn.text
        )
        lines.append(f"- recent_dialogue: {recent}")
    lines.append(
        "- instruction: Never re-ask for facts already present in this summary. Persist any newly learned "
        "objective, success criteria, stakeholder role, constraints, or open question into the run state."
    )
    return "\n".join(lines)


def should_include_bootstrap(state: OnboardingState | None) -> bool:
    if state is None:
        return True
    return (
        state.state == "intake"
        and state.source.system == "unknown"
        and not state.conversation_history
        and not state.project_objective
    )


def heuristic_research_for_state(state: OnboardingState) -> ResearchSummary:
    template = _HEURISTIC_RESEARCH.get(state.source.system)
    if template is None:
        return ResearchSummary(
            status="blocked",
            source_system=state.source.system,
            summary=f"No built-in research notes for {state.source.system}.",
            note="Need live research or customer-provided source documentation.",
            open_questions=["Please share any source docs, exports, or access details you have."],
            researched_at=datetime.now(timezone.utc),
        )
    return ResearchSummary(
        status="heuristic",
        source_system=state.source.system,  # type: ignore[arg-type]
        summary=template["summary"],
        doc_urls=list(template["doc_urls"]),
        likely_access_paths=list(template["likely_access_paths"]),
        known_quirks=list(template["known_quirks"]),
        open_questions=list(template["open_questions"]),
        note=template["note"],
        researched_at=datetime.now(timezone.utc),
    )


def build_recommended_plan(state: OnboardingState) -> RecommendedPlan:
    research = state.research_summary
    access = state.source.access_method
    if access == "unknown" and research.likely_access_paths:
        access = research.likely_access_paths[0]

    steps = [
        f"Confirm the deployment model and access path for {state.source.system}.",
        "Collect one representative sample for invoices, customers, and contacts or confirm which objects matter first.",
        "Validate credentials or agree on the recurring export/drop workflow.",
        "Draft the mapping contract and review success criteria before code generation.",
    ]
    risks = []
    if state.source.system == "epicor":
        risks.append("Epicor access varies by deployment and customization, so collection may require admin help.")
    if access == "unknown":
        risks.append("Access path is still unknown; implementation cannot begin until it is clarified.")
    assumptions = []
    if state.tables_in_scope:
        assumptions.append(f"Initial object scope is {', '.join(state.tables_in_scope)}.")
    if state.project_objective:
        assumptions.append(f"Project objective: {state.project_objective}")

    summary = (
        f"Recommended next move: determine whether {state.source.system} data will come via "
        f"{access if access != 'unknown' else 'API, export, or file drop'}, then collect one sample "
        "or credential path so discovery can proceed without repeated intake questions."
    )
    return RecommendedPlan(
        summary=summary,
        recommended_access_method=access,  # type: ignore[arg-type]
        steps=steps,
        risks=risks,
        assumptions=assumptions,
        updated_at=datetime.now(timezone.utc),
    )
