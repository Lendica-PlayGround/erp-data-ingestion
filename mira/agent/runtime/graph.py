"""LangGraph ReAct agent wiring (PRD §2.3)."""

from __future__ import annotations

import os

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from agent.models.onboarding import OnboardingState
from agent.runtime.bootstrap import load_bootstrap_text
from agent.runtime.context import RunContext
from agent.runtime.tools import build_mira_tools


def _model() -> BaseChatModel:
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise RuntimeError(
            "OPENAI_API_KEY is required for LangGraph chat mode. "
            "Export it or use `mira doctor` to verify configuration."
        )
    model = os.getenv("MIRA_OPENAI_MODEL", "gpt-4o-mini")
    return ChatOpenAI(model=model, temperature=0)


def build_mira_graph(ctx: RunContext, state: OnboardingState | None = None):
    """Return a compiled LangGraph runnable: invoke with `{"messages": [...]}`."""
    tools = build_mira_tools(ctx)
    system = load_bootstrap_text(state=state)
    return create_react_agent(_model(), tools, prompt=system)
