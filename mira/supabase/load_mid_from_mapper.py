from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import boto3
import psycopg

MIRA_ROOT = Path(__file__).resolve().parents[1]
if str(MIRA_ROOT) not in sys.path:
    sys.path.insert(0, str(MIRA_ROOT))

from framework.mid_db_loader import (
    batch_context,
    complete_load_batch,
    create_load_batch,
    log_validation_failure,
    parse_mid_row,
    upsert_mid_rows,
)
from framework.csv_writer import build_artifact_manifest
from framework.observability import build_run_event, publish_run_events


def _load_repo_dotenv(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or key in os.environ:
            continue
        if value[:1] == value[-1:] and value[:1] in {"'", '"'}:
            value = value[1:-1]
        os.environ[key] = value


def _connection_kwargs() -> dict[str, str]:
    return {
        "host": os.environ["POSTGRES_HOST"],
        "port": os.environ.get("POSTGRES_PORT", "5432"),
        "dbname": os.environ["POSTGRES_DB"],
        "user": os.environ["POSTGRES_USER"],
        "password": os.environ["POSTGRES_PASSWORD"],
        "sslmode": os.environ.get("POSTGRES_SSLMODE", "require"),
    }


def _default_mapper(repo_root: Path) -> Path:
    return repo_root / "phase2.5" / "output" / "handshake_run_mapper.py"


def _run_mapper(*, mapper: Path, table: str, input_path: Path, output_dir: Path) -> Path:
    argv = [
        sys.executable,
        str(mapper),
        "--input",
        str(input_path),
        "--output",
        str(output_dir),
        "--table",
        table,
    ]
    subprocess.run(argv, cwd=mapper.parent, check=True)
    mapped_csv = output_dir / f"{table}_mapped.csv"
    if not mapped_csv.is_file():
        raise FileNotFoundError(f"Mapper did not produce expected CSV: {mapped_csv}")
    return mapped_csv


def _read_rows_with_failures(mid_table: str, csv_path: Path) -> tuple[list[dict], list[tuple[int, dict, str]]]:
    import csv

    rows: list[dict] = []
    failures: list[tuple[int, dict, str]] = []
    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"CSV has no header: {csv_path}")
        for row_number, row in enumerate(reader, start=2):
            try:
                parsed = parse_mid_row(mid_table, row)
                _validate_mid_row(mid_table, parsed)
                rows.append(parsed)
            except Exception as exc:  # noqa: BLE001 - record row-level validation failures
                failures.append((row_number, row, str(exc)))
    return rows, failures


REQUIRED_ROW_FIELDS: dict[str, tuple[str, ...]] = {
    "customers": (
        "external_id",
        "_source_system",
        "_source_record_id",
        "_company_id",
        "_ingested_at",
        "_source_file",
        "_mapping_version",
        "_row_hash",
    ),
    "contacts": (
        "external_id",
        "_source_system",
        "_source_record_id",
        "_company_id",
        "_ingested_at",
        "_source_file",
        "_mapping_version",
        "_row_hash",
    ),
    "invoices": (
        "external_id",
        "_source_system",
        "_source_record_id",
        "_company_id",
        "_ingested_at",
        "_source_file",
        "_mapping_version",
        "_row_hash",
    ),
}

ENUM_ROW_FIELDS: dict[str, dict[str, set[str]]] = {
    "customers": {"status": {"ACTIVE", "ARCHIVED"}},
    "contacts": {},
    "invoices": {
        "type": {"ACCOUNTS_RECEIVABLE", "ACCOUNTS_PAYABLE"},
        "status": {"DRAFT", "OPEN", "PAID", "UNCOLLECTIBLE", "VOID", "PARTIALLY_PAID", "SUBMITTED"},
    },
}


def _validate_mid_row(mid_table: str, row: dict[str, object]) -> None:
    for field in REQUIRED_ROW_FIELDS[mid_table]:
        value = row.get(field)
        if value in (None, ""):
            raise ValueError(f"Missing required field: {field}")

    for field, allowed in ENUM_ROW_FIELDS[mid_table].items():
        value = row.get(field)
        if value in (None, ""):
            continue
        if str(value) not in allowed:
            raise ValueError(f"Invalid {field}: {value}")


def _write_validation_report(
    report_path: Path,
    *,
    table: str,
    valid_rows: list[dict],
    failures: list[tuple[int, dict, str]],
) -> dict[str, object]:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "table": table,
        "status": "failed" if failures else "completed",
        "valid_row_count": len(valid_rows),
        "failure_count": len(failures),
        "failures": [
            {
                "row_number": row_number,
                "source_record_id": raw_row.get("_source_record_id"),
                "row_hash": raw_row.get("_row_hash"),
                "error_message": error_message,
            }
            for row_number, raw_row, error_message in failures
        ],
    }
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def _require_run_id() -> str:
    run_id = os.environ.get("MIRA_RUN_ID", "").strip()
    if not run_id:
        raise SystemExit("Set MIRA_RUN_ID before running the mid-layer loader.")
    return run_id


def _final_batch_status(*, valid_row_count: int, failure_count: int) -> str:
    if failure_count > 0 or valid_row_count == 0:
        return "failed"
    return "completed"


def _storage_bucket() -> str:
    bucket = os.environ.get("SUPABASE_STORAGE_S3_BUCKET", "").strip()
    if not bucket:
        raise SystemExit("Set SUPABASE_STORAGE_S3_BUCKET before running the mid-layer loader.")
    return bucket


def _storage_client():
    return boto3.client(
        "s3",
        endpoint_url=os.environ.get("SUPABASE_STORAGE_S3_ENDPOINT_URL"),
        aws_access_key_id=os.environ.get("SUPABASE_STORAGE_S3_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("SUPABASE_STORAGE_S3_SECRET_ACCESS_KEY"),
        region_name=os.environ.get("SUPABASE_STORAGE_S3_REGION"),
    )


def _publish_events_if_configured(events: list[dict[str, object]]) -> None:
    host = os.environ.get("CLICKHOUSE_HOST", "").strip()
    database = os.environ.get("CLICKHOUSE_DATABASE", "").strip()
    username = os.environ.get("CLICKHOUSE_USERNAME", "").strip()
    password = os.environ.get("CLICKHOUSE_PASSWORD", "").strip()
    if not all([host, database, username, password]):
        return
    try:
        publish_run_events(
            events,
            host=host,
            database=database,
            username=username,
            password=password,
        )
    except Exception:  # noqa: BLE001 - analytics should not fail a committed batch
        return


def _persist_artifacts_and_build_metadata(
    *,
    company_id: str,
    table_name: str,
    load_batch_id: int,
    run_id: str,
    source_input: Path,
    mapped_csv: Path,
    validation_report_path: Path,
    status: str,
    sync_type: str,
    inserted_count: int,
    updated_count: int,
    failed_count: int,
    s3_client=None,
) -> dict[str, object]:
    bucket = _storage_bucket()
    artifact_paths = {
        "raw": source_input,
        "mapped": mapped_csv,
        "validation": validation_report_path,
    }
    client = s3_client or _storage_client()
    artifact_manifest = build_artifact_manifest(
        company_id=company_id,
        run_id=run_id,
        load_batch_id=str(load_batch_id),
        artifacts=artifact_paths,
    )
    for artifact_type, path in artifact_paths.items():
        client.upload_file(str(path), bucket, artifact_manifest["artifacts"][artifact_type]["storage_key"])
    run_event = build_run_event(
        "load_batch_completed",
        company_id=company_id,
        run_id=run_id,
        load_batch_id=str(load_batch_id),
        table_name=table_name,
        severity="info" if status == "completed" else "warning",
        payload={
            "sync_type": sync_type,
            "status": status,
            "inserted_count": inserted_count,
            "updated_count": updated_count,
            "failed_count": failed_count,
        },
    )
    manifest_key = f"{artifact_manifest['artifact_prefix']}/manifests/{table_name}_manifest.json"
    artifact_manifest["storage_key"] = manifest_key
    client.put_object(
        Bucket=bucket,
        Key=manifest_key,
        Body=json.dumps(artifact_manifest, indent=2).encode("utf-8"),
        ContentType="application/json",
    )
    return {
        "storage_bucket": bucket,
        "artifact_manifest": artifact_manifest,
        "validation_report_storage_key": artifact_manifest["artifacts"]["validation"]["storage_key"],
        "run_events": [run_event],
    }


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    _load_repo_dotenv(repo_root / ".env")
    run_id = _require_run_id()

    parser = argparse.ArgumentParser(
        description="Run the generated handshake mapper and load its mid-layer CSV output into Supabase Postgres.",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path(os.environ.get("MID_LOADER_INPUT_PATH", "")) if os.environ.get("MID_LOADER_INPUT_PATH") else None,
        help="Source CSV to feed through the generated mapper.",
    )
    parser.add_argument(
        "--table",
        choices=("customers", "contacts", "invoices"),
        default=os.environ.get("MID_LOADER_TABLE") or None,
        help="Mid-layer table slug to generate and load.",
    )
    parser.add_argument(
        "--mapper",
        type=Path,
        default=Path(os.environ["MID_LOADER_MAPPER_PATH"]) if os.environ.get("MID_LOADER_MAPPER_PATH") else _default_mapper(repo_root),
        help="Path to the generated handshake_run_mapper.py script.",
    )
    parser.add_argument(
        "--sync-type",
        choices=("initial", "delta"),
        default=os.environ.get("MID_LOADER_SYNC_TYPE", "delta"),
        help="Load batch sync type recorded in Supabase.",
    )
    args = parser.parse_args()

    if args.input is None:
        raise SystemExit("Provide --input or set MID_LOADER_INPUT_PATH in .env.")
    if args.table is None:
        raise SystemExit("Provide --table or set MID_LOADER_TABLE in .env.")
    if not args.input.is_file():
        raise SystemExit(f"Input file not found: {args.input}")
    if not args.mapper.is_file():
        raise SystemExit(f"Mapper script not found: {args.mapper}")

    with tempfile.TemporaryDirectory(prefix="mid-loader-") as temp_dir:
        temp_path = Path(temp_dir)
        mapped_csv = _run_mapper(
            mapper=args.mapper.resolve(),
            table=args.table,
            input_path=args.input.resolve(),
            output_dir=temp_path,
        )

        valid_rows, failures = _read_rows_with_failures(args.table, mapped_csv)
        validation_report_path = temp_path / "validation" / f"{args.table}_report.json"
        _write_validation_report(
            validation_report_path,
            table=args.table,
            valid_rows=valid_rows,
            failures=failures,
        )
        context = batch_context(
            args.table,
            valid_rows,
            source_input=args.input.resolve(),
            mapped_csv=mapped_csv,
            sync_type=args.sync_type,
        )

        with psycopg.connect(**_connection_kwargs()) as conn:
            with conn.cursor() as cur:
                load_batch_id = create_load_batch(cur, context)
                for row_number, raw_row, error_message in failures:
                    log_validation_failure(
                        cur,
                        load_batch_id=load_batch_id,
                        company_id=context["company_id"],
                        entity_name=args.table,
                        source_system=context["source_system"],
                        source_record_id=raw_row.get("_source_record_id"),
                        row_number=row_number,
                        row_hash=raw_row.get("_row_hash"),
                        error_code="mid_csv_validation",
                        error_message=error_message,
                        raw_row=raw_row,
                    )

                inserted_count, updated_count = upsert_mid_rows(cur, args.table, load_batch_id, valid_rows)
                status = _final_batch_status(valid_row_count=len(valid_rows), failure_count=len(failures))
                metadata = _persist_artifacts_and_build_metadata(
                    company_id=str(context["company_id"]),
                    table_name=args.table,
                    load_batch_id=load_batch_id,
                    run_id=run_id,
                    source_input=args.input.resolve(),
                    mapped_csv=mapped_csv,
                    validation_report_path=validation_report_path,
                    status=status,
                    sync_type=str(context["sync_type"]),
                    inserted_count=inserted_count,
                    updated_count=updated_count,
                    failed_count=len(failures),
                )
                complete_load_batch(
                    cur,
                    load_batch_id=load_batch_id,
                    status=status,
                    inserted_count=inserted_count,
                    updated_count=updated_count,
                    failed_count=len(failures),
                    metadata=metadata,
                )
            conn.commit()
        _publish_events_if_configured(metadata["run_events"])

    print(
        f"Loaded {len(valid_rows)} {args.table} row(s) into mid_{args.table} "
        f"with {len(failures)} validation failure(s)."
    )


if __name__ == "__main__":
    main()
