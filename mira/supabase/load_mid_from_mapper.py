from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

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
                rows.append(parse_mid_row(mid_table, row))
            except Exception as exc:  # noqa: BLE001 - record row-level validation failures
                failures.append((row_number, row, str(exc)))
    return rows, failures


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    _load_repo_dotenv(repo_root / ".env")

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
        mapped_csv = _run_mapper(
            mapper=args.mapper.resolve(),
            table=args.table,
            input_path=args.input.resolve(),
            output_dir=Path(temp_dir),
        )

        valid_rows, failures = _read_rows_with_failures(args.table, mapped_csv)
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
                status = "completed" if valid_rows else "failed"
                complete_load_batch(
                    cur,
                    load_batch_id=load_batch_id,
                    status=status,
                    inserted_count=inserted_count,
                    updated_count=updated_count,
                    failed_count=len(failures),
                )
            conn.commit()

    print(
        f"Loaded {len(valid_rows)} {args.table} row(s) into mid_{args.table} "
        f"with {len(failures)} validation failure(s)."
    )


if __name__ == "__main__":
    main()
