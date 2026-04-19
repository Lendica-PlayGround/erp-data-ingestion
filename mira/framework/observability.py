"""OpenTelemetry hooks → ClickHouse (stub; wire exporters in deployment)."""

from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

import httpx

logger = logging.getLogger(__name__)

RUN_EVENTS_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS run_events (
    event_time String,
    event_type String,
    company_id String,
    run_id String,
    load_batch_id String,
    table_name String,
    severity String,
    payload_json String
) ENGINE = MergeTree
ORDER BY (run_id, event_time)
"""


def build_run_event(
    event_type: str,
    *,
    company_id: str,
    run_id: str,
    load_batch_id: str | None,
    table_name: str | None,
    severity: str,
    payload: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "event_time": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "company_id": company_id,
        "run_id": run_id,
        "load_batch_id": load_batch_id,
        "table_name": table_name,
        "severity": severity,
        "payload_json": payload or {},
    }


def publish_run_events(
    events: list[dict[str, object]],
    *,
    host: str,
    database: str,
    username: str,
    password: str,
    client=httpx,
) -> None:
    if not events:
        return

    base_url = host.rstrip("/")
    ddl_url = f"{base_url}/?database={database}"
    client.post(
        ddl_url,
        content=RUN_EVENTS_TABLE_DDL,
        auth=(username, password),
        headers={"Content-Type": "text/plain"},
        timeout=20.0,
    ).raise_for_status()

    url = f"{base_url}/?database={database}&query=INSERT%20INTO%20run_events%20FORMAT%20JSONEachRow"
    rows = []
    for event in events:
        rows.append(
            {
                "event_time": str(event.get("event_time", "")),
                "event_type": str(event.get("event_type", "")),
                "company_id": str(event.get("company_id", "")),
                "run_id": str(event.get("run_id", "")),
                "load_batch_id": str(event.get("load_batch_id") or ""),
                "table_name": str(event.get("table_name") or ""),
                "severity": str(event.get("severity", "")),
                "payload_json": json.dumps(event.get("payload_json", {}), separators=(",", ":")),
            }
        )
    payload = "\n".join(json.dumps(row, separators=(",", ":")) for row in rows)
    response = client.post(
        url,
        content=payload,
        auth=(username, password),
        headers={"Content-Type": "application/json"},
        timeout=20.0,
    )
    response.raise_for_status()


@contextmanager
def span(name: str, **attrs: object) -> Iterator[None]:
    _ = attrs
    logger.debug("span start %s", name)
    try:
        yield
    finally:
        logger.debug("span end %s", name)
