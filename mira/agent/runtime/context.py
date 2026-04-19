from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

from agent.stores.base import StateStore


@dataclass
class RunContext:
    store: StateStore
    run_id: UUID
    workspace_root: Path = field(default_factory=lambda: Path.cwd() / ".mira_workspace")
    notify: Callable[[str], None] | None = None

    def emit(self, text: str) -> None:
        if self.notify:
            self.notify(text)
