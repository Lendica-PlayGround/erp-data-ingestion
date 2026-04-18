from __future__ import annotations

import json
from typing import Any, List

from erp_data_ingestion.models import RunMetadataRecord, TelemetryEvent


class ClickHouseTelemetrySink:
    def __init__(
        self,
        client: Any | None = None,
        *,
        host: str | None = None,
        port: int | None = None,
        username: str | None = None,
        password: str | None = None,
        database: str | None = None,
        secure: bool | None = None,
    ) -> None:
        self.client = client or self._build_default_client(
            host=host,
            port=port,
            username=username,
            password=password,
            database=database,
            secure=secure,
        )

    def write_run(
        self,
        *,
        run_metadata: RunMetadataRecord,
        telemetry_events: List[TelemetryEvent],
    ) -> None:
        self.client.insert(
            "phase4_run_metadata",
            [
                [
                    run_metadata.run_id,
                    run_metadata.company_id,
                    run_metadata.table,
                    run_metadata.sync_type,
                    run_metadata.schema_version,
                    run_metadata.source_path,
                    run_metadata.output_path,
                    run_metadata.row_count,
                    run_metadata.status,
                    json.dumps(run_metadata.validation_summary, sort_keys=True),
                ]
            ],
            column_names=[
                "run_id",
                "company_id",
                "table",
                "sync_type",
                "schema_version",
                "source_path",
                "output_path",
                "row_count",
                "status",
                "validation_summary_json",
            ],
        )

        event_rows = [
            [
                event.event_name,
                event.occurred_at.isoformat(),
                json.dumps(event.attributes, sort_keys=True),
            ]
            for event in telemetry_events
        ]
        self.client.insert(
            "phase4_telemetry_events",
            event_rows,
            column_names=["event_name", "occurred_at", "attributes_json"],
        )

    def _build_default_client(
        self,
        *,
        host: str | None,
        port: int | None,
        username: str | None,
        password: str | None,
        database: str | None,
        secure: bool | None,
    ) -> Any:
        try:
            import clickhouse_connect
        except ImportError as exc:
            raise RuntimeError(
                "clickhouse-connect is required for the default ClickHouse client"
            ) from exc

        kwargs = {
            "host": host,
            "port": port,
            "username": username,
            "password": password,
            "database": database,
            "secure": secure,
        }
        filtered_kwargs = {key: value for key, value in kwargs.items() if value is not None}
        return clickhouse_connect.get_client(**filtered_kwargs)
