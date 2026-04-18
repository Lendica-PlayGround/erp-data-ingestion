from __future__ import annotations

import json
import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, List

import pyarrow as pa
import pyarrow.parquet as pq

from erp_data_ingestion.models import RunMetadataRecord, TelemetryEvent
from erp_data_ingestion.serializers import get_serializer


@dataclass
class LakeWriteResult:
    output_path: Path
    manifest_path: Path
    row_count: int
    table: str
    schema_version: str
    validation_summary: Dict[str, int]
    run_metadata: RunMetadataRecord
    telemetry_events: List[TelemetryEvent]


class Phase4Transformer:
    def __init__(self, schema_version: str) -> None:
        self.schema_version = schema_version

    def build_output_path(
        self,
        output_root: Path,
        company_id: str,
        table: str,
        sync_type: str,
        run_id: str,
        logical_date: date,
    ) -> Path:
        return (
            output_root
            / f"company_id={company_id}"
            / f"table={table}"
            / f"sync_type={sync_type}"
            / f"date={logical_date.isoformat()}"
            / f"run_id={run_id}"
            / f"{table}.parquet"
        )

    def transform_midlayer_csv(
        self,
        input_csv: Path,
        output_root: Path,
        table: str,
        company_id: str,
        sync_type: str,
        run_id: str,
        logical_date: date,
    ) -> LakeWriteResult:
        rows = list(self._read_csv(input_csv, table))
        output_path = self.build_output_path(
            output_root=output_root,
            company_id=company_id,
            table=table,
            sync_type=sync_type,
            run_id=run_id,
            logical_date=logical_date,
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)

        arrow_table = pa.Table.from_pylist(rows)
        pq.write_table(arrow_table, output_path)

        validation_summary = {"invalid_rows": 0}
        run_metadata = RunMetadataRecord(
            run_id=run_id,
            company_id=company_id,
            table=table,
            sync_type=sync_type,
            schema_version=self.schema_version,
            source_path=str(input_csv),
            output_path=str(output_path),
            row_count=len(rows),
            status="success",
            validation_summary=validation_summary,
        )
        telemetry_events = [
            TelemetryEvent(
                event_name="phase4.transform.completed",
                attributes={
                    "company_id": company_id,
                    "table": table,
                    "sync_type": sync_type,
                    "run_id": run_id,
                    "row_count": len(rows),
                    "invalid_rows": 0,
                    "schema_version": self.schema_version,
                },
            )
        ]
        manifest_path = output_path.with_name("manifest.json")
        manifest_payload = {
            "run_id": run_id,
            "company_id": company_id,
            "table": table,
            "sync_type": sync_type,
            "schema_version": self.schema_version,
            "source_path": str(input_csv),
            "output_path": str(output_path),
            "row_count": len(rows),
            "validation_summary": validation_summary,
        }
        manifest_path.write_text(
            json.dumps(manifest_payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )

        return LakeWriteResult(
            output_path=output_path,
            manifest_path=manifest_path,
            row_count=len(rows),
            table=table,
            schema_version=self.schema_version,
            validation_summary=validation_summary,
            run_metadata=run_metadata,
            telemetry_events=telemetry_events,
        )

    def _read_csv(self, input_csv: Path, table: str) -> Iterable[Dict[str, Any]]:
        serializer = get_serializer(table=table, schema_version=self.schema_version)
        with input_csv.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                yield serializer.serialize_row(row)
