from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Mapping

from erp_data_ingestion.phase4 import LakeWriteResult, Phase4Transformer


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
    SUPPORTED_TABLES: tuple[str, ...] = ("invoice", "contact", "customer")

    def __init__(self, *, output_root: Path) -> None:
        self.output_root = output_root

    def _validate_run_id(self, run_id: str) -> None:
        if not run_id or not run_id.strip():
            raise ValueError("run_id must not be empty or whitespace")
        if run_id in {".", ".."}:
            raise ValueError("run_id must not be a reserved path segment")
        if "/" in run_id or "\\" in run_id:
            raise ValueError("run_id must not contain path separators")

    def _validate_input_paths(self, input_paths: Mapping[str, Path]) -> None:
        keys = set(input_paths)
        missing = [table for table in self.SUPPORTED_TABLES if table not in keys]
        extra = [key for key in keys if key not in self.SUPPORTED_TABLES]
        messages = []
        if missing:
            messages.append(f"missing override for {', '.join(missing)}")
        if extra:
            messages.append(f"unsupported override keys: {', '.join(extra)}")
        if messages:
            raise ValueError("; ".join(messages))

    def _resolve_inputs(self, request: Phase4DemoRequest) -> dict[str, Path]:
        if request.input_paths:
            self._validate_input_paths(request.input_paths)
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

    def _build_table_entry(
        self,
        *,
        schema_version: str,
        csv_path: Path,
        result: LakeWriteResult | None,
        status: str,
        error: str | None = None,
    ) -> Phase4DemoTableResult:
        if result is None:
            return Phase4DemoTableResult(
                status=status,
                row_count=0,
                schema_version=schema_version,
                input_path=str(csv_path),
                parquet_path=None,
                manifest_path=None,
                error=error,
            )
        return Phase4DemoTableResult(
            status=status,
            row_count=result.row_count,
            schema_version=schema_version,
            input_path=str(csv_path),
            parquet_path=str(result.output_path),
            manifest_path=str(result.manifest_path),
            error=error,
        )

    def run(self, request: Phase4DemoRequest) -> Phase4DemoResult:
        self._validate_run_id(request.run_id)
        run_root = self.output_root / request.run_id
        if run_root.exists():
            raise ValueError(f"run_id already exists: {request.run_id}")

        inputs = self._resolve_inputs(request)
        logical_date = date.today()
        started_at = datetime.now(timezone.utc).isoformat()

        run_root.mkdir(parents=True, exist_ok=True)
        tables: dict[str, Phase4DemoTableResult] = {}
        overall_status = "succeeded"
        last_error: str | None = None

        for table in self.SUPPORTED_TABLES:
            csv_path = inputs[table]
            schema_version = f"{table}.v1"
            transformer = Phase4Transformer(schema_version=schema_version)
            table_result: LakeWriteResult | None = None
            try:
                if not csv_path.exists():
                    raise FileNotFoundError(f"missing input for {table}: {csv_path}")
                table_result = transformer.transform_midlayer_csv(
                    input_csv=csv_path,
                    output_root=run_root,
                    table=table,
                    company_id=request.company_id,
                    sync_type=request.sync_type,
                    run_id=request.run_id,
                    logical_date=logical_date,
                )
                tables[table] = self._build_table_entry(
                    schema_version=schema_version,
                    csv_path=csv_path,
                    result=table_result,
                    status="succeeded",
                )
            except Exception as exc:
                overall_status = "failed"
                last_error = str(exc)
                tables[table] = self._build_table_entry(
                    schema_version=schema_version,
                    csv_path=csv_path,
                    result=None,
                    status="failed",
                    error=str(exc),
                )
                break

        finished_at = datetime.now(timezone.utc).isoformat()
        payload: dict[str, object] = {
            "run_id": request.run_id,
            "company_id": request.company_id,
            "mode": "dry-run",
            "dataset": request.dataset,
            "sync_type": request.sync_type,
            "status": overall_status,
            "started_at": started_at,
            "finished_at": finished_at,
            "tables": {name: asdict(value) for name, value in tables.items()},
            "events": [],
            "last_error": last_error,
        }

        state_path = self._write_state(run_root, payload)
        return Phase4DemoResult(
            run_id=request.run_id,
            company_id=request.company_id,
            status=overall_status,
            tables=tables,
            run_state_path=state_path,
        )
