"""CLI entrypoint: `mira` — init runs, Telegram, local chat, dashboard."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from uuid import UUID, uuid4

from agent.models.onboarding import OnboardingState, SourceProfile
from agent.runtime.context import RunContext
from agent.runtime.graph import build_mira_graph
from agent.runtime.telegram_bot import run_polling
from agent.stores.supabase_store import store_from_env


def _workspace() -> Path:
    return Path(os.getenv("MIRA_WORKSPACE", ".mira_workspace")).resolve()


def cmd_init(args: argparse.Namespace) -> int:
    store = store_from_env()
    rid = uuid4()
    company = args.company_id
    st = OnboardingState(
        run_id=rid,
        company_id=company,
        source=SourceProfile(system=args.source_system),
        tables_in_scope=args.tables.split(",") if args.tables else [],
    )
    store.put(st)
    print(f"run_id={rid}")
    print(f"company_id={company}")
    print("Export MIRA_RUN_ID for Telegram / chat, or pass --run-id.")
    return 0


def cmd_chat(args: argparse.Namespace) -> int:
    store = store_from_env()
    rid = UUID(args.run_id)
    st = store.get(rid)
    if st is None:
        print("Unknown run_id", file=sys.stderr)
        return 1
    ctx = RunContext(store=store, run_id=rid, workspace_root=_workspace())
    graph = build_mira_graph(ctx)
    msg = args.message
    out = graph.invoke({"messages": [("user", msg)]})
    last = out["messages"][-1]
    print(getattr(last, "content", last))
    return 0


def cmd_telegram(args: argparse.Namespace) -> int:
    store = store_from_env()
    rid_str = os.environ.get("MIRA_RUN_ID") or getattr(args, "run_id", "")
    if not rid_str:
        print("Set MIRA_RUN_ID or pass --run-id", file=sys.stderr)
        return 1
    rid = UUID(rid_str)
    st = store.get(rid)
    if st is None:
        print("Unknown run_id — run `mira init` first.", file=sys.stderr)
        return 1
    run_polling(store, st, _workspace())
    return 0


def cmd_doctor(_: argparse.Namespace) -> int:
    ok = True
    if not os.getenv("OPENAI_API_KEY"):
        print("OPENAI_API_KEY missing — LangGraph chat/Telegram model calls will fail.")
        ok = False
    if not os.getenv("TELEGRAM_BOT_TOKEN"):
        print("TELEGRAM_BOT_TOKEN missing — Telegram mode unavailable.")
    if os.getenv("SUPABASE_URL"):
        print("Supabase URL present — persistence enabled when service role key set.")
    else:
        print("Supabase env absent — using in-memory state store.")
    return 0 if ok else 2


def cmd_dashboard(_: argparse.Namespace) -> int:
    try:
        from agent.runtime.dashboard_app import run_dashboard
    except ImportError as e:
        print("Dashboard dependencies missing:", e, file=sys.stderr)
        return 1
    host = os.getenv("MIRA_DASHBOARD_HOST", "127.0.0.1")
    port = int(os.getenv("MIRA_DASHBOARD_PORT", "8090"))
    run_dashboard(host, port)
    return 0


def main() -> None:
    p = argparse.ArgumentParser(prog="mira", description="Mira onboarding agent (Phase 2–3).")
    sub = p.add_subparsers(dest="cmd", required=True)

    i = sub.add_parser("init", help="Create onboarding run in configured store")
    i.add_argument("company_id")
    i.add_argument("--source-system", default="unknown")
    i.add_argument("--tables", default="invoice,customer,contact")
    i.set_defaults(func=cmd_init)

    c = sub.add_parser("chat", help="Single-turn LangGraph invoke (needs OPENAI_API_KEY)")
    c.add_argument("--run-id", required=True)
    c.add_argument("message")
    c.set_defaults(func=cmd_chat)

    t = sub.add_parser("telegram", help="Poll Telegram (needs TELEGRAM_BOT_TOKEN, MIRA_RUN_ID)")
    t.add_argument("--run-id", default=os.getenv("MIRA_RUN_ID", ""))
    t.set_defaults(func=cmd_telegram)

    d = sub.add_parser("doctor", help="Print environment readiness")
    d.set_defaults(func=cmd_doctor)

    b = sub.add_parser("dashboard", help="Run JWT dashboard stub (pip install .[dashboard])")
    b.set_defaults(func=cmd_dashboard)

    args = p.parse_args()
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
