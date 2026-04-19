from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

from erp_data_ingestion.demo_dataset import FixedPhase4DemoDataset
from erp_data_ingestion.phase4 import Phase4Transformer


@dataclass
class Phase4DemoRunResult:
    status: str
    tables: list[dict[str, Any]]
    last_error: str | None = None


class Phase4DemoRunner:
    def __init__(
        self,
        *,
        output_root: Path,
        publisher: Any,
        on_progress: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.output_root = output_root
        self.publisher = publisher
        self.on_progress = on_progress or (lambda _: None)

    def run(self, *, dataset: FixedPhase4DemoDataset, run_id: str) -> Phase4DemoRunResult:
        started_at = datetime.now(timezone.utc).isoformat()
        table_summaries: list[dict[str, Any]] = []
        self.on_progress(
            {
                "status": "running",
                "started_at": started_at,
                "run_id": run_id,
                "tables": [],
            }
        )
        try:
            for table in dataset.tables:
                transformer = Phase4Transformer(schema_version=table.schema_version)
                logical_date = date.fromisoformat(table.logical_date)
                lake_result = transformer.transform_midlayer_csv(
                    input_csv=table.source_csv,
                    output_root=self.output_root,
                    table=table.table_name,
                    company_id=dataset.company_id,
                    sync_type=table.sync_type,
                    run_id=run_id,
                    logical_date=logical_date,
                )
                published = self.publisher.publish(lake_result)
                summary = {
                    "table": table.table_name,
                    "status": "succeeded",
                    "source_csv": str(table.source_csv),
                    "row_count": lake_result.row_count,
                    "output_parquet_uri": published.parquet_uri,
                    "manifest_uri": published.manifest_uri,
                    "error": None,
                }
                table_summaries.append(summary)
                self.on_progress(
                    {
                        "status": "running",
                        "run_id": run_id,
                        "tables": table_summaries,
                    }
                )
        except Exception as exc:
            message = str(exc)
            self.on_progress(
                {
                    "status": "failed",
                    "run_id": run_id,
                    "tables": table_summaries,
                    "last_error": message,
                }
            )
            return Phase4DemoRunResult(
                status="failed",
                tables=table_summaries,
                last_error=message,
            )
        self.on_progress(
            {
                "status": "succeeded",
                "run_id": run_id,
                "tables": table_summaries,
                "last_error": None,
            }
        )
        return Phase4DemoRunResult(status="succeeded", tables=table_summaries)
