from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any
from uuid import UUID

from agent.models.onboarding import OnboardingState


class StateStore(ABC):
    """All skill mutations go through here (PRD §2.5 `state_store`)."""

    @abstractmethod
    def get(self, run_id: UUID) -> OnboardingState | None: ...

    @abstractmethod
    def put(self, state: OnboardingState) -> None: ...

    @abstractmethod
    def patch(self, run_id: UUID, patch: dict[str, Any], actor: str) -> OnboardingState:
        """Merge patch into stored document; returns updated state."""
