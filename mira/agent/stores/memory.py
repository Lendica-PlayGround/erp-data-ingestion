from __future__ import annotations

import copy
from typing import Any
from uuid import UUID

from agent.models.onboarding import OnboardingState
from agent.stores.base import StateStore


class InMemoryStateStore(StateStore):
    def __init__(self) -> None:
        self._rows: dict[UUID, OnboardingState] = {}

    def get(self, run_id: UUID) -> OnboardingState | None:
        row = self._rows.get(run_id)
        return copy.deepcopy(row) if row else None

    def put(self, state: OnboardingState) -> None:
        self._rows[state.run_id] = copy.deepcopy(state)

    def patch(self, run_id: UUID, patch: dict[str, Any], actor: str) -> OnboardingState:
        _ = actor
        current = self.get(run_id)
        if current is None:
            raise KeyError(f"Unknown run_id {run_id}")
        current.apply_patch(patch)
        self.put(current)
        return copy.deepcopy(current)
