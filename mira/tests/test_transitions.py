from datetime import datetime, timezone
from uuid import uuid4

import pytest

from agent.models.onboarding import Approval, OnboardingState, SourceProfile
from agent.runtime.transitions import assert_transition, transition_allowed


def test_intake_to_research_requires_system():
    rid = uuid4()
    st = OnboardingState(run_id=rid, company_id="c", source=SourceProfile(system="unknown"))
    ok, _ = transition_allowed(st, "research")
    assert ok is False
    st.source.system = "stripe"
    ok2, _ = transition_allowed(st, "research")
    assert ok2 is True


def test_awaiting_approval_to_code_requires_both_signatures():
    rid = uuid4()
    st = OnboardingState(
        run_id=rid,
        company_id="c",
        state="awaiting_approval",
        approval=Approval(),
    )
    with pytest.raises(ValueError):
        assert_transition(st, "code")
    st.approval.customer_confirmed_at = datetime.now(timezone.utc)
    with pytest.raises(ValueError):
        assert_transition(st, "code")
    st.approval.fde_confirmed_at = datetime.now(timezone.utc)
    assert_transition(st, "code")
