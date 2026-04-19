"""OpenTelemetry hooks → ClickHouse (stub; wire exporters in deployment)."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Iterator

logger = logging.getLogger(__name__)


@contextmanager
def span(name: str, **attrs: object) -> Iterator[None]:
    _ = attrs
    logger.debug("span start %s", name)
    try:
        yield
    finally:
        logger.debug("span end %s", name)
