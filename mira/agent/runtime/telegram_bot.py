"""Telegram binding: allowlist, mention gate, approval slash commands (PRD §1.3, §2.4)."""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from uuid import UUID

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from agent.models.onboarding import OnboardingState
from agent.runtime.context import RunContext
from agent.runtime.graph import build_mira_graph
from agent.stores.base import StateStore

logger = logging.getLogger(__name__)


def _parse_allowlist(raw: str | None) -> set[int]:
    if not raw:
        return set()
    out: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            out.add(int(part))
    return out


def _require_mention(update: Update, bot_username: str | None) -> bool:
    if os.getenv("TELEGRAM_REQUIRE_MENTION", "true").lower() not in ("1", "true", "yes"):
        return True
    if not bot_username or not update.message or not update.message.text:
        return False
    return f"@{bot_username}" in update.message.text


async def cmd_approve_customer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    store: StateStore = context.application.bot_data["store"]
    run_id = UUID(context.application.bot_data["run_id"])
    allow = _parse_allowlist(os.getenv("TELEGRAM_CUSTOMER_USER_IDS"))
    uid = update.effective_user.id if update.effective_user else None
    if allow and uid not in allow:
        await update.message.reply_text("Not authorized for /approve_customer.")
        return
    if store.get(run_id) is None:
        await update.message.reply_text("Run not found.")
        return
    patch = {
        "approval": {
            "customer_confirmed_at": datetime.now(timezone.utc).isoformat(),
            "customer_telegram_user_id": str(uid) if uid is not None else None,
        }
    }
    store.patch(run_id, patch, "telegram_customer_approve")
    await update.message.reply_text("Customer approval recorded.")


async def cmd_approve_fde(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    store: StateStore = context.application.bot_data["store"]
    run_id = UUID(context.application.bot_data["run_id"])
    allow = _parse_allowlist(os.getenv("TELEGRAM_FDE_USER_IDS"))
    uid = update.effective_user.id if update.effective_user else None
    if allow and uid not in allow:
        await update.message.reply_text("Not authorized for /approve_fde.")
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
    await update.message.reply_text("FDE approval recorded.")


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return
    me = await context.bot.get_me()
    if not _require_mention(update, me.username):
        return
    allow = _parse_allowlist(os.getenv("TELEGRAM_ALLOWLIST_USER_IDS"))
    uid = update.effective_user.id if update.effective_user else None
    if allow and uid not in allow:
        await update.message.reply_text("Not in allowlist for this bot.")
        return

    store: StateStore = context.application.bot_data["store"]
    run_id = UUID(context.application.bot_data["run_id"])
    ws = context.application.bot_data["workspace"]

    ctx_sync = RunContext(store=store, run_id=run_id, workspace_root=ws, notify=lambda _m: None)
    try:
        graph = build_mira_graph(ctx_sync)
    except Exception as e:
        await update.message.reply_text(f"Agent misconfigured: {e}")
        return
    msg = update.message.text.replace(f"@{me.username}", "").strip()

    def _invoke():
        return graph.invoke({"messages": [("user", msg)]})

    try:
        out = await asyncio.to_thread(_invoke)
    except Exception as e:
        logger.exception("agent failed")
        await update.message.reply_text(f"Agent error: {e}")
        return
    last = out["messages"][-1]
    content = getattr(last, "content", str(last))
    await update.message.reply_text(str(content)[:3500])


def run_polling(store: StateStore, run: OnboardingState, workspace) -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    app = Application.builder().token(token).build()
    app.bot_data["store"] = store
    app.bot_data["run_id"] = str(run.run_id)
    app.bot_data["workspace"] = workspace
    # Telegram command names use underscores; map PRD /approve-customer to /approve_customer in BotFather.
    app.add_handler(CommandHandler("approve_customer", cmd_approve_customer))
    app.add_handler(CommandHandler("approve_fde", cmd_approve_fde))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    print("Mira Telegram polling started. Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)
