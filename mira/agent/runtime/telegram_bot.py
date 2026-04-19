"""Telegram binding for Mira's onboarding-group UX."""

from __future__ import annotations

import asyncio
import logging
import os
from collections import defaultdict, deque
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from agent.models.onboarding import OnboardingState
from agent.runtime.context import RunContext
from agent.runtime.graph import build_mira_graph
from agent.runtime.session_memory import (
    append_conversation_turn,
    answers_open_question,
    redact_credentials,
    record_telegram_sender_context,
    message_has_onboarding_signal,
    maybe_capture_message_facts,
    recent_dialogue_messages,
)
from agent.stores.base import StateStore

logger = logging.getLogger(__name__)

SenderRole = Literal["customer", "fde", "other"]
MAX_TELEGRAM_MESSAGE_LEN = 3500
MAX_TELEGRAM_REPLY_PARTS = 3


@dataclass(slots=True)
class TelegramMessageContext:
    text: str
    sender_role: SenderRole
    is_private_chat: bool
    is_reply_to_bot: bool
    mentions_bot: bool
    has_attachment: bool


class ChatRateLimiter:
    def __init__(self, min_seconds_between_replies: int, max_replies_per_minute: int) -> None:
        self.min_seconds_between_replies = min_seconds_between_replies
        self.max_replies_per_minute = max_replies_per_minute
        self._history: dict[int, deque[datetime]] = defaultdict(deque)

    def consume(self, chat_id: int | None, *, now: datetime | None = None) -> bool:
        if chat_id is None:
            return True
        ts = now or datetime.now(timezone.utc)
        window = self._history[chat_id]
        while window and (ts - window[0]).total_seconds() > 60:
            window.popleft()
        if window and (ts - window[-1]).total_seconds() < self.min_seconds_between_replies:
            return False
        if len(window) >= self.max_replies_per_minute:
            return False
        window.append(ts)
        return True


def _parse_allowlist(raw: str | None) -> set[int]:
    if not raw:
        return set()
    out: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            out.add(int(part))
    return out


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("invalid integer for %s=%r; using %s", name, raw, default)
        return default


def _message_allowlist() -> set[int]:
    return _parse_allowlist(os.getenv("TELEGRAM_ALLOWLIST_USER_IDS"))


def _customer_allowlist() -> set[int]:
    return _parse_allowlist(os.getenv("TELEGRAM_CUSTOMER_USER_IDS"))


def _fde_allowlist() -> set[int]:
    return _parse_allowlist(os.getenv("TELEGRAM_FDE_USER_IDS"))


def _command_allowlist() -> set[int]:
    return _message_allowlist() | _customer_allowlist() | _fde_allowlist()


def _is_message_authorized(user_id: int | None) -> bool:
    allow = _message_allowlist()
    return not allow or user_id in (allow | _customer_allowlist() | _fde_allowlist())


def _is_command_authorized(user_id: int | None) -> bool:
    allow = _command_allowlist()
    return not allow or user_id in allow


def _is_private_chat(update: Update) -> bool:
    return bool(update.effective_chat and update.effective_chat.type == "private")


def _is_reply_to_bot(update: Update, bot_username: str | None) -> bool:
    if not update.message or not update.message.reply_to_message:
        return False
    replied_user = update.message.reply_to_message.from_user
    if not replied_user:
        return False
    if replied_user.is_bot and update.get_bot() and replied_user.id == update.get_bot().id:
        return True
    return bool(bot_username and replied_user.username == bot_username)


def resolve_sender_role(user_id: int | None) -> SenderRole:
    if user_id in _customer_allowlist():
        return "customer"
    if user_id in _fde_allowlist():
        return "fde"
    return "other"


def _mentions_bot(text: str, bot_username: str | None) -> bool:
    return bool(bot_username and f"@{bot_username}" in text)


def _legacy_should_respond(context: TelegramMessageContext, require_mention: bool) -> bool:
    return context.is_private_chat or context.is_reply_to_bot or (not require_mention) or context.mentions_bot


def should_respond(
    context: TelegramMessageContext,
    state: OnboardingState,
    *,
    smart_policy: bool,
    require_mention: bool,
    window_messages: int,
    window_seconds: int,
) -> bool:
    if not smart_policy:
        return _legacy_should_respond(context, require_mention)
    if context.is_private_chat:
        return True
    if state.ui_preferences.telegram.muted:
        return False
    if context.is_reply_to_bot or context.mentions_bot:
        return True
    if context.sender_role in {"customer", "fde"} and (
        answers_open_question(
            state,
            context.text,
            window_messages=window_messages,
            window_seconds=window_seconds,
        )
        or message_has_onboarding_signal(context.text, has_attachment=context.has_attachment)
    ):
        return True
    return False


def _meaningful_message(update: Update) -> bool:
    message = update.message
    if not message:
        return False
    return bool(
        message.text
        or message.caption
        or message.document
        or message.photo
        or message.video
        or message.audio
        or message.voice
    )


def _message_text(update: Update, bot_username: str | None) -> str:
    if not update.message:
        return ""
    raw = update.message.text or update.message.caption or ""
    if bot_username:
        raw = raw.replace(f"@{bot_username}", "")
    return raw.strip()


def _has_attachment(update: Update) -> bool:
    if not update.message:
        return False
    return bool(
        update.message.document
        or update.message.photo
        or update.message.video
        or update.message.audio
        or update.message.voice
    )


def _attachment_summary(update: Update) -> str:
    if not update.message:
        return ""
    message = update.message
    if message.document:
        return f"attachment: {message.document.file_name or 'document'}"
    if message.photo:
        return "attachment: photo"
    if message.video:
        return "attachment: video"
    if message.audio:
        return "attachment: audio"
    if message.voice:
        return "attachment: voice note"
    return ""


def _conversation_text(update: Update, bot_username: str | None) -> str:
    text = _message_text(update, bot_username)
    attachment_summary = _attachment_summary(update)
    if attachment_summary and text:
        return f"{attachment_summary}\n{text}"
    return attachment_summary or text


def _sender_full_name(update: Update) -> str:
    user = update.effective_user
    if not user:
        return "unknown"
    full_name = " ".join(part for part in [user.first_name, user.last_name] if part).strip()
    if full_name:
        return full_name
    if user.username:
        return user.username
    return str(user.id)


def _split_reply(text: str, limit: int = MAX_TELEGRAM_MESSAGE_LEN) -> list[str]:
    text = redact_credentials(text).strip()
    if not text:
        return []
    if len(text) <= limit:
        return [text]
    parts: list[str] = []
    paragraphs = [chunk.strip() for chunk in text.split("\n\n") if chunk.strip()]
    current = ""
    for paragraph in paragraphs:
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            parts.append(current)
            current = ""
        while len(paragraph) > limit:
            parts.append(paragraph[:limit].rstrip())
            paragraph = paragraph[limit:].lstrip()
        current = paragraph
    if current:
        parts.append(current)
    if not parts:
        parts = [text[:limit]]
    return parts[:MAX_TELEGRAM_REPLY_PARTS]


async def _reply_text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    *,
    rate_limit: bool = True,
) -> bool:
    if not update.message:
        return False
    chat_id = update.effective_chat.id if update.effective_chat else None
    limiter: ChatRateLimiter = context.application.bot_data["rate_limiter"]
    parts = _split_reply(text)
    if not parts:
        return False
    for index, part in enumerate(parts):
        if index > 0:
            await asyncio.sleep(limiter.min_seconds_between_replies)
        if rate_limit and not limiter.consume(chat_id):
            logger.warning("telegram reply dropped by rate limiter for chat_id=%s", chat_id)
            return index > 0
        if index == 0:
            await update.message.reply_text(part)
        else:
            await context.bot.send_message(chat_id=chat_id, text=part)
    return True


async def _typing_loop(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    while True:
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        await asyncio.sleep(4)


def _status_text(state: OnboardingState) -> str:
    pending_approvals = []
    if state.approval.customer_confirmed_at is None:
        pending_approvals.append("customer")
    if state.approval.fde_confirmed_at is None:
        pending_approvals.append("fde")
    blockers = "; ".join(redact_credentials(blocker.message) for blocker in state.blockers) or "none"
    return "\n".join(
        [
            f"Phase: {state.state}",
            f"Next question: {redact_credentials(state.next_question or 'none')}",
            f"Pending approvals: {', '.join(pending_approvals) if pending_approvals else 'none'}",
            f"Blockers: {blockers}",
            f"Muted: {'yes' if state.ui_preferences.telegram.muted else 'no'}",
        ]
    )


def _plan_text(state: OnboardingState) -> str:
    lines = [redact_credentials(state.recommended_plan.summary or "No recommended plan yet.")]
    steps = state.recommended_plan.steps[:5]
    if steps:
        lines.append("")
        lines.extend(f"{idx}. {redact_credentials(step)}" for idx, step in enumerate(steps, start=1))
    return "\n".join(lines)


def _mute_patch(muted: bool, user_id: int | None) -> dict[str, object]:
    return {
        "ui_preferences": {
            "telegram": {
                "muted": muted,
                "muted_at": datetime.now(timezone.utc).isoformat() if muted else None,
                "muted_by_user_id": str(user_id) if muted and user_id is not None else None,
            }
        }
    }


async def _on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("telegram update failed: %r", update, exc_info=context.error)


async def cmd_approve_customer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    store: StateStore = context.application.bot_data["store"]
    run_id = UUID(context.application.bot_data["run_id"])
    allow = _parse_allowlist(os.getenv("TELEGRAM_CUSTOMER_USER_IDS"))
    uid = update.effective_user.id if update.effective_user else None
    if allow and uid not in allow:
        await _reply_text(update, context, "Not authorized for /approve_customer.")
        return
    if store.get(run_id) is None:
        await _reply_text(update, context, "Run not found.")
        return
    patch = {
        "approval": {
            "customer_confirmed_at": datetime.now(timezone.utc).isoformat(),
            "customer_telegram_user_id": str(uid) if uid is not None else None,
        }
    }
    store.patch(run_id, patch, "telegram_customer_approve")
    await _reply_text(update, context, "Customer approval recorded.")


async def cmd_approve_fde(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    store: StateStore = context.application.bot_data["store"]
    run_id = UUID(context.application.bot_data["run_id"])
    allow = _parse_allowlist(os.getenv("TELEGRAM_FDE_USER_IDS"))
    uid = update.effective_user.id if update.effective_user else None
    if allow and uid not in allow:
        await _reply_text(update, context, "Not authorized for /approve_fde.")
        return
    uname = update.effective_user.username if update.effective_user else None
    patch = {
        "approval": {
            "fde_confirmed_at": datetime.now(timezone.utc).isoformat(),
            "fde_telegram_user_id": str(uid) if uid is not None else None,
            "fde_user": uname,
        }
    }
    store.patch(run_id, patch, "telegram_fde_approve")
    await _reply_text(update, context, "FDE approval recorded.")


async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    me = await context.bot.get_me()
    chat = update.effective_chat
    user = update.effective_user
    await _reply_text(
        update,
        context,
        "pong\n"
        f"bot=@{me.username}\n"
        f"chat_id={chat.id if chat else 'unknown'} chat_type={chat.type if chat else 'unknown'}\n"
        f"user_id={user.id if user else 'unknown'} username={user.username if user else 'unknown'}"
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id if update.effective_user else None
    if not _is_command_authorized(uid):
        await _reply_text(update, context, "Not in allowlist for this bot.")
        return
    store: StateStore = context.application.bot_data["store"]
    run_id = UUID(context.application.bot_data["run_id"])
    current = store.get(run_id)
    if current is None:
        await _reply_text(update, context, "Run not found.")
        return
    await _reply_text(update, context, _status_text(current))


async def cmd_plan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id if update.effective_user else None
    if not _is_command_authorized(uid):
        await _reply_text(update, context, "Not in allowlist for this bot.")
        return
    store: StateStore = context.application.bot_data["store"]
    run_id = UUID(context.application.bot_data["run_id"])
    current = store.get(run_id)
    if current is None:
        await _reply_text(update, context, "Run not found.")
        return
    await _reply_text(update, context, _plan_text(current))


async def cmd_quiet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id if update.effective_user else None
    if not _is_command_authorized(uid):
        await _reply_text(update, context, "Not in allowlist for this bot.")
        return
    store: StateStore = context.application.bot_data["store"]
    run_id = UUID(context.application.bot_data["run_id"])
    if store.get(run_id) is None:
        await _reply_text(update, context, "Run not found.")
        return
    store.patch(run_id, _mute_patch(True, uid), "telegram_quiet")
    await _reply_text(update, context, "Muted. I'll still watch and remember. /resume to turn me back on.")


async def cmd_resume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id if update.effective_user else None
    if not _is_command_authorized(uid):
        await _reply_text(update, context, "Not in allowlist for this bot.")
        return
    store: StateStore = context.application.bot_data["store"]
    run_id = UUID(context.application.bot_data["run_id"])
    if store.get(run_id) is None:
        await _reply_text(update, context, "Run not found.")
        return
    store.patch(run_id, _mute_patch(False, uid), "telegram_resume")
    await _reply_text(update, context, "Resumed. I'll respond again when it looks like the message is for me.")


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _meaningful_message(update):
        return
    me = await context.bot.get_me()
    text = _message_text(update, me.username)
    has_attachment = _has_attachment(update)
    storage_text = _conversation_text(update, me.username)
    logger.info(
        "telegram message chat_id=%s chat_type=%s user_id=%s username=%s text=%r",
        update.effective_chat.id if update.effective_chat else None,
        update.effective_chat.type if update.effective_chat else None,
        update.effective_user.id if update.effective_user else None,
        update.effective_user.username if update.effective_user else None,
        storage_text,
    )
    uid = update.effective_user.id if update.effective_user else None
    store: StateStore = context.application.bot_data["store"]
    run_id = UUID(context.application.bot_data["run_id"])
    ws = context.application.bot_data["workspace"]
    channel = f"telegram:{update.effective_chat.id}" if update.effective_chat else "telegram"
    sender_role = resolve_sender_role(uid)
    message_context = TelegramMessageContext(
        text=text,
        sender_role=sender_role,
        is_private_chat=_is_private_chat(update),
        is_reply_to_bot=_is_reply_to_bot(update, me.username),
        mentions_bot=_mentions_bot(update.message.text or update.message.caption or "", me.username),
        has_attachment=has_attachment,
    )
    smart_policy = _env_bool("MIRA_TG_SMART_POLICY", True)
    require_mention = _env_bool("TELEGRAM_REQUIRE_MENTION", False)
    window_messages = _env_int("MIRA_TG_OPEN_QUESTION_WINDOW_MESSAGES", 8)
    window_seconds = _env_int("MIRA_TG_OPEN_QUESTION_WINDOW_SECONDS", 900)
    current = store.get(run_id)
    if current is None:
        if _legacy_should_respond(message_context, require_mention):
            await _reply_text(update, context, "Run not found.")
        return
    should_reply = should_respond(
        message_context,
        current,
        smart_policy=smart_policy,
        require_mention=require_mention,
        window_messages=window_messages,
        window_seconds=window_seconds,
    )
    if not _is_message_authorized(uid):
        logger.info(
            "telegram message rejected: user_id=%s not in allowlist=%s",
            uid,
            sorted(_message_allowlist()),
        )
        if should_reply:
            await _reply_text(update, context, "Not in allowlist for this bot.")
        return
    current = maybe_capture_message_facts(store, run_id, storage_text)
    if current is None:
        await _reply_text(update, context, "Run not found.")
        return
    current = record_telegram_sender_context(
        store,
        run_id,
        user_id=uid,
        username=update.effective_user.username if update.effective_user else None,
        full_name=_sender_full_name(update),
        role=sender_role,
    )
    if current is None:
        await _reply_text(update, context, "Run not found.")
        return
    current = append_conversation_turn(store, run_id, "user", storage_text, channel=channel)
    if current is None:
        await _reply_text(update, context, "Run not found.")
        return
    should_reply = should_respond(
        message_context,
        current,
        smart_policy=smart_policy,
        require_mention=require_mention,
        window_messages=window_messages,
        window_seconds=window_seconds,
    )
    if not should_reply:
        logger.info("telegram message logged without reply")
        return
    if has_attachment:
        reply = (
            "Received the attachment. I'll remember it for onboarding context, but I can't parse "
            "attachments yet in this MVP."
        )
        if await _reply_text(update, context, reply):
            append_conversation_turn(store, run_id, "assistant", reply, channel=channel)
        return
    ctx_sync = RunContext(store=store, run_id=run_id, workspace_root=ws, notify=lambda _m: None)
    try:
        graph = build_mira_graph(ctx_sync, state=current)
    except Exception as e:
        logger.exception("agent misconfigured")
        await _reply_text(update, context, f"Agent misconfigured: {e}")
        return
    chat_id = update.effective_chat.id if update.effective_chat else None
    typing_task = None
    if chat_id is not None:
        typing_task = asyncio.create_task(_typing_loop(context, chat_id))

    def _invoke():
        return graph.invoke({"messages": recent_dialogue_messages(current)})

    try:
        out = await asyncio.to_thread(_invoke)
    except Exception as e:
        logger.exception("agent failed")
        if typing_task is not None:
            typing_task.cancel()
            with suppress(asyncio.CancelledError):
                await typing_task
        await _reply_text(update, context, f"Agent error: {e}")
        return
    if typing_task is not None:
        typing_task.cancel()
        with suppress(asyncio.CancelledError):
            await typing_task
    last = out["messages"][-1]
    content = redact_credentials(str(getattr(last, "content", str(last))))
    if await _reply_text(update, context, content):
        append_conversation_turn(store, run_id, "assistant", content, channel=channel)


def run_polling(store: StateStore, run: OnboardingState, workspace) -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    logging.basicConfig(
        level=os.getenv("MIRA_TELEGRAM_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    app = Application.builder().token(token).build()
    app.bot_data["store"] = store
    app.bot_data["run_id"] = str(run.run_id)
    app.bot_data["workspace"] = workspace
    app.bot_data["rate_limiter"] = ChatRateLimiter(
        min_seconds_between_replies=_env_int("MIRA_TG_MIN_SECONDS_BETWEEN_REPLIES", 3),
        max_replies_per_minute=_env_int("MIRA_TG_MAX_REPLIES_PER_MINUTE", 10),
    )
    app.add_error_handler(_on_error)
    # Telegram command names use underscores; map PRD /approve-customer to /approve_customer in BotFather.
    app.add_handler(CommandHandler("ping", cmd_ping))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("plan", cmd_plan))
    app.add_handler(CommandHandler("quiet", cmd_quiet))
    app.add_handler(CommandHandler("resume", cmd_resume))
    app.add_handler(CommandHandler("approve_customer", cmd_approve_customer))
    app.add_handler(CommandHandler("approve_fde", cmd_approve_fde))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, on_message))
    print("Mira Telegram polling started. Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)
