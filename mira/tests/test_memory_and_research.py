from uuid import uuid4

from agent.models.onboarding import OnboardingState, SourceProfile
from agent.runtime.bootstrap import load_bootstrap_text
from agent.runtime.session_memory import (
    append_conversation_turn,
    maybe_capture_message_facts,
    recent_dialogue_messages,
)
from agent.runtime.tools import _research_vendor_impl
from agent.runtime.context import RunContext
from agent.stores.memory import InMemoryStateStore


def test_load_bootstrap_only_for_true_cold_start():
    rid = uuid4()
    cold = OnboardingState(run_id=rid, company_id="c", source=SourceProfile(system="unknown"))
    warm = OnboardingState(run_id=rid, company_id="c", source=SourceProfile(system="epicor"))
    warm.conversation_history = []

    cold_prompt = load_bootstrap_text(state=cold)
    warm_prompt = load_bootstrap_text(state=warm)

    assert "<!-- BOOTSTRAP.md -->" in cold_prompt
    assert "<!-- BOOTSTRAP.md -->" not in warm_prompt
    assert "source.system: epicor" in warm_prompt


def test_message_fact_capture_infers_epicor_and_seeds_research():
    store = InMemoryStateStore()
    rid = uuid4()
    store.put(OnboardingState(run_id=rid, company_id="acme", source=SourceProfile(system="unknown")))

    updated = maybe_capture_message_facts(store, rid, "I am currently using Epicor and have no idea.")

    assert updated is not None
    assert updated.source.system == "epicor"
    assert updated.state == "research"
    assert updated.research_summary.status == "heuristic"
    assert "Epicor onboarding usually starts" in updated.research_summary.summary
    assert updated.recommended_plan.summary
    assert updated.next_question == updated.research_summary.open_questions[0]


def test_recent_dialogue_messages_replays_latest_turns():
    store = InMemoryStateStore()
    rid = uuid4()
    store.put(OnboardingState(run_id=rid, company_id="acme", source=SourceProfile(system="epicor")))

    append_conversation_turn(store, rid, "user", "We are on Epicor.", channel="telegram")
    append_conversation_turn(store, rid, "assistant", "What access do you have?", channel="telegram")
    append_conversation_turn(store, rid, "user", "I have no idea.", channel="telegram")

    state = store.get(rid)
    assert state is not None
    assert recent_dialogue_messages(state) == [
        ("user", "We are on Epicor."),
        ("assistant", "What access do you have?"),
        ("user", "I have no idea."),
    ]


def test_research_vendor_without_tavily_stores_heuristic_plan(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    store = InMemoryStateStore()
    rid = uuid4()
    state = OnboardingState(run_id=rid, company_id="acme", source=SourceProfile(system="epicor"))
    store.put(state)
    ctx = RunContext(store=store, run_id=rid)

    out = _research_vendor_impl(ctx, str(rid), "")
    refreshed = store.get(rid)

    assert '"ok": true' in out.lower()
    assert refreshed is not None
    assert refreshed.research_summary.status == "heuristic"
    assert refreshed.recommended_plan.recommended_access_method in {
        "api_key",
        "csv_export",
        "shared_drive",
        "sftp",
    }
    assert any(blocker.code == "research_unavailable" for blocker in refreshed.blockers)
