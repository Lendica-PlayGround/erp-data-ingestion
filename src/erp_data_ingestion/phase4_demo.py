from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path

from erp_data_ingestion.phase4 import Phase4Transformer


@dataclass
class Phase4DemoRequest:
    run_id: str
    company_id: str
    dataset: str
    sync_type: str
    input_paths: dict[str, Path] = field(default_factory=dict)
    seed_root: Path | None = None


@dataclass
class Phase4DemoTableResult:
    status: str
    row_count: int
    schema_version: str
    input_path: str
    parquet_path: str | None = None
    manifest_path: str | None = None
    error: str | None = None


@dataclass
class Phase4DemoResult:
    run_id: str
    company_id: str
    status: str
    tables: dict[str, Phase4DemoTableResult]
    run_state_path: Path


class Phase4DemoRunner:
    def __init__(self, *, output_root: Path) -> None:
        self.output_root = output_root

    def _resolve_inputs(self, request: Phase4DemoRequest) -> dict[str, Path]:
        if request.input_paths:
            return dict(request.input_paths)

        seed_root = request.seed_root or Path("seeds/samples/midlayer-csv")
        return {
            "invoice": seed_root / "invoice.csv",
            "contact": seed_root / "contact.csv",
            "customer": seed_root / "customer.csv",
        }

    def _write_state(self, run_root: Path, payload: dict[str, object]) -> Path:
        run_root.mkdir(parents=True, exist_ok=True)
        path = run_root / "run_state.json"
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return path

    def run(self, request: Phase4DemoRequest) -> Phase4DemoResult:
        run_root = self.output_root / request.run_id
        run_root.mkdir(parents=True, exist_ok=True)
        inputs = self._resolve_inputs(request)
        logical_date = date.today()
        started_at = datetime.utcnow().isoformat() + "Z"

        tables: dict[str, Phase4DemoTableResult] = {}

        for table, csv_path in inputs.items():
            if not csv_path.exists():
                raise FileNotFoundError(f"missing input for {table}: {csv_path}")

            schema_version = f"{table}.v1"
            transformer = Phase4Transformer(schema_version=schema_version)
            result = transformer.transform_midlayer_csv(
                input_csv=csv_path,
                output_root=run_root,
                table=table,
                company_id=request.company_id,
                sync_type=request.sync_type,
                run_id=request.run_id,
                logical_date=logical_date,
            )
            tables[table] = Phase4DemoTableResult(
                status="succeeded",
                row_count=result.row_count,
                schema_version=schema_version,
                input_path=str(csv_path),
                parquet_path=str(result.output_path),
                manifest_path=str(result.manifest_path),
            )

        finished_at = datetime.utcnow().isoformat() + "Z"
        payload: dict[str, object] = {
            "run_id": request.run_id,
            "company_id": request.company_id,
            "mode": "dry-run",
            "dataset": request.dataset,
            "sync_type": request.sync_type,
            "status": "succeeded",
            "started_at": started_at,
            "finished_at": finished_at,
            "tables": {name: asdict(value) for name, value in tables.items()},
            "events": [],
            "last_error": None,
        }

        state_path = self._write_state(run_root, payload)
        return Phase4DemoResult(
            run_id=request.run_id,
            company_id=request.company_id,
            status="succeeded",
            tables=tables,
            run_state_path=state_path,
        )
