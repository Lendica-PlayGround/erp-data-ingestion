"""DataConnector ABC — PRD §5.3 / framework layout."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import Any


class DataConnector(ABC):
    @abstractmethod
    def extract_initial(self, limit: int | None = None) -> Iterator[dict[str, Any]]:
        """Yield raw source records for historical backfill."""

    @abstractmethod
    def extract_delta(self, cursor: str | None) -> tuple[Iterator[dict[str, Any]], str | None]:
        """Yield changed records and the next cursor token."""
