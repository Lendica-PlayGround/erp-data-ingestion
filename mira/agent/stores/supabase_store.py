"""Supabase Postgres backend for onboarding state (optional dependency)."""

from __future__ import annotations

import json
import os
from typing import Any
from uuid import UUID

from agent.models.onboarding import OnboardingState
from agent.stores.base import StateStore
from agent.stores.memory import InMemoryStateStore


class SupabaseStateStore(StateStore):
    """Uses Supabase REST API with service role key (same env as Phase 1)."""

    def __init__(self, url: str | None = None, service_key: str | None = None) -> None:
        try:
            from supabase import create_client
        except ImportError as e:
            raise ImportError(
                "Install supabase extra: pip install erp-mira-agent[supabase]"
            ) from e

        self._url = url or os.environ["SUPABASE_URL"]
        self._key = service_key or os.environ["SUPABASE_SERVICE_ROLE_KEY"]
        self._client = create_client(self._url, self._key)
        self._table = os.environ.get("MIRA_ONBOARDING_TABLE", "onboarding_runs")

    def get(self, run_id: UUID) -> OnboardingState | None:
        res = (
            self._client.table(self._table)
            .select("document")
            .eq("run_id", str(run_id))
            .limit(1)
            .execute()
        )
        if not res.data:
            return None
        doc = res.data[0]["document"]
        if isinstance(doc, str):
            doc = json.loads(doc)
        return OnboardingState.model_validate(doc)

    def put(self, state: OnboardingState) -> None:
        payload = {
            "run_id": str(state.run_id),
            "company_id": state.company_id,
            "state": state.state,
            "document": state.model_dump(mode="json"),
        }
        self._client.table(self._table).upsert(payload, on_conflict="run_id").execute()

    def patch(self, run_id: UUID, patch: dict[str, Any], actor: str) -> OnboardingState:
        current = self.get(run_id)
        if current is None:
            raise KeyError(f"Unknown run_id {run_id}")
        current.apply_patch(patch)
        _ = actor
        self.put(current)
        out = self.get(run_id)
        if out is None:
            raise RuntimeError("State missing after upsert")
        return out


def store_from_env() -> StateStore:
    if os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_SERVICE_ROLE_KEY"):
        return SupabaseStateStore()
    return InMemoryStateStore()
