from datetime import datetime, timedelta, timezone
from uuid import uuid4

from agent.models.onboarding import ConversationTurn, OnboardingState, SourceProfile
from agent.runtime.telegram_bot import (
    ChatRateLimiter,
    TelegramMessageContext,
    _mute_patch,
    _status_text,
    resolve_sender_role,
    should_respond,
)
from agent.stores.memory import InMemoryStateStore


def _state_with_open_question() -> OnboardingState:
    now = datetime.now(timezone.utc)
    return OnboardingState(
        run_id=uuid4(),
        company_id="acme",
        source=SourceProfile(system="epicor"),
        next_question="Do you use Epicor cloud or on-prem?",
        conversation_history=[
            ConversationTurn(
                role="assistant",
                text="Do you use Epicor cloud or on-prem?",
                channel="telegram:1",
                created_at=now - timedelta(minutes=2),
            )
        ],
    )


def _context(
    text: str,
    *,
    sender_role: str = "customer",
    mentions_bot: bool = False,
    has_attachment: bool = False,
) -> TelegramMessageContext:
    return TelegramMessageContext(
        text=text,
        sender_role=sender_role,  # type: ignore[arg-type]
        is_private_chat=False,
        is_reply_to_bot=False,
        mentions_bot=mentions_bot,
        has_attachment=has_attachment,
    )


def test_resolve_sender_role_from_env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_CUSTOMER_USER_IDS", "11")
    monkeypatch.setenv("TELEGRAM_FDE_USER_IDS", "22")

    assert resolve_sender_role(11) == "customer"
    assert resolve_sender_role(22) == "fde"
    assert resolve_sender_role(33) == "other"


def test_should_respond_to_customer_answering_open_question_without_mention():
    state = _state_with_open_question()

    assert should_respond(
        _context("on-prem, version 11"),
        state,
        smart_policy=True,
        require_mention=False,
        window_messages=8,
        window_seconds=900,
    )


def test_should_stay_silent_for_other_side_chatter():
    state = _state_with_open_question()

    assert not should_respond(
        _context("James, can you confirm timeline?", sender_role="other"),
        state,
        smart_policy=True,
        require_mention=False,
        window_messages=8,
        window_seconds=900,
    )


def test_should_drop_non_command_auto_reply_when_muted():
    state = _state_with_open_question()
    state.ui_preferences.telegram.muted = True

    assert not should_respond(
        _context("on-prem, version 11"),
        state,
        smart_policy=True,
        require_mention=False,
        window_messages=8,
        window_seconds=900,
    )


def test_signal_message_and_status_redact_credentials():
    state = _state_with_open_question()
    state.blockers = []
    state.next_question = "Paste api_key: sk_test_abcdefghijklmnopqrstuvwxyz"

    assert should_respond(
        _context("Here is our API key: sk_test_abcdefghijklmnopqrstuvwxyz"),
        state,
        smart_policy=True,
        require_mention=False,
        window_messages=8,
        window_seconds=900,
    )
    assert "sk_test_" not in _status_text(state)
    assert "[redacted credential]" in _status_text(state)


def test_rate_limiter_enforces_spacing_and_minute_cap():
    limiter = ChatRateLimiter(min_seconds_between_replies=3, max_replies_per_minute=2)
    base = datetime(2026, 4, 19, 12, 0, tzinfo=timezone.utc)

    assert limiter.consume(123, now=base)
    assert not limiter.consume(123, now=base + timedelta(seconds=1))
    assert limiter.consume(123, now=base + timedelta(seconds=3))
    assert not limiter.consume(123, now=base + timedelta(seconds=10))
    assert limiter.consume(123, now=base + timedelta(seconds=61))


def test_mute_patch_round_trip():
    store = InMemoryStateStore()
    state = OnboardingState(run_id=uuid4(), company_id="acme", source=SourceProfile(system="epicor"))
    store.put(state)

    store.patch(state.run_id, _mute_patch(True, 42), "test_quiet")
    muted = store.get(state.run_id)
    assert muted is not None
    assert muted.ui_preferences.telegram.muted is True
    assert muted.ui_preferences.telegram.muted_by_user_id == "42"

    store.patch(state.run_id, _mute_patch(False, 42), "test_resume")
    resumed = store.get(state.run_id)
    assert resumed is not None
    assert resumed.ui_preferences.telegram.muted is False
    assert resumed.ui_preferences.telegram.muted_at is None
