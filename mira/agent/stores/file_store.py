"""JSON-file state store for local development.

Persists `OnboardingState` to a single JSON file on disk so `mira init` and
`mira telegram` (separate processes) can share state without Supabase. Not
safe for concurrent writers; intended for single-dev workstation use only.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any
from uuid import UUID

from agent.models.onboarding import OnboardingState
from agent.stores.base import StateStore


class FileStateStore(StateStore):
    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._write_all({})

    def _read_all(self) -> dict[str, dict[str, Any]]:
        try:
            return json.loads(self._path.read_text(encoding="utf-8")) or {}
        except json.JSONDecodeError:
            return {}

    def _write_all(self, rows: dict[str, dict[str, Any]]) -> None:
        tmp_fd, tmp_name = tempfile.mkstemp(
            dir=str(self._path.parent), prefix=".state.", suffix=".json.tmp"
        )
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
                json.dump(rows, fh, indent=2, sort_keys=True, default=str)
            os.replace(tmp_name, self._path)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise

    def get(self, run_id: UUID) -> OnboardingState | None:
        rows = self._read_all()
        row = rows.get(str(run_id))
        if row is None:
            return None
        return OnboardingState.model_validate(row)

    def put(self, state: OnboardingState) -> None:
        rows = self._read_all()
        rows[str(state.run_id)] = json.loads(state.model_dump_json())
        self._write_all(rows)

    def patch(self, run_id: UUID, patch: dict[str, Any], actor: str) -> OnboardingState:
        _ = actor
        current = self.get(run_id)
        if current is None:
            raise KeyError(f"Unknown run_id {run_id}")
        current.apply_patch(patch)
        self.put(current)
        return current
