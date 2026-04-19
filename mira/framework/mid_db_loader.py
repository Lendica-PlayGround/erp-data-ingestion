from __future__ import annotations

import csv
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from psycopg import sql
from psycopg.types.json import Jsonb


MID_TABLE_COLUMNS: dict[str, list[str]] = {
    "customers": [
        "external_id",
        "name",
        "is_supplier",
        "is_customer",
        "email_address",
        "tax_number",
        "status",
        "currency",
        "remote_updated_at",
        "phone_number",
        "addresses",
        "remote_was_deleted",
        "_unmapped",
        "_source_system",
        "_source_record_id",
        "_company_id",
        "_ingested_at",
        "_source_file",
        "_mapping_version",
        "_row_hash",
    ],
    "contacts": [
        "external_id",
        "first_name",
        "last_name",
        "account_external_id",
        "addresses",
        "email_addresses",
        "phone_numbers",
        "last_activity_at",
        "remote_created_at",
        "remote_was_deleted",
        "_unmapped",
        "_source_system",
        "_source_record_id",
        "_company_id",
        "_ingested_at",
        "_source_file",
        "_mapping_version",
        "_row_hash",
    ],
    "invoices": [
        "external_id",
        "type",
        "number",
        "contact_external_id",
        "issue_date",
        "due_date",
        "paid_on_date",
        "memo",
        "currency",
        "exchange_rate",
        "total_discount",
        "sub_total",
        "total_tax_amount",
        "total_amount",
        "balance",
        "status",
        "remote_was_deleted",
        "_unmapped",
        "_source_system",
        "_source_record_id",
        "_company_id",
        "_ingested_at",
        "_source_file",
        "_mapping_version",
        "_row_hash",
    ],
}

BOOLEAN_FIELDS: dict[str, set[str]] = {
    "customers": {"is_supplier", "is_customer", "remote_was_deleted"},
    "contacts": {"remote_was_deleted"},
    "invoices": {"remote_was_deleted"},
}

DEFAULT_VALUES: dict[str, dict[str, Any]] = {
    "customers": {
        "is_supplier": False,
        "is_customer": True,
        "remote_was_deleted": False,
        "_unmapped": {},
    },
    "contacts": {
        "remote_was_deleted": False,
        "_unmapped": {},
    },
    "invoices": {
        "remote_was_deleted": False,
        "_unmapped": {},
    },
}

JSON_FIELDS: dict[str, set[str]] = {
    "customers": {"_unmapped"},
    "contacts": {"_unmapped"},
    "invoices": {"_unmapped"},
}

DATETIME_FIELDS: dict[str, set[str]] = {
    "customers": {"remote_updated_at", "_ingested_at"},
    "contacts": {"last_activity_at", "remote_created_at", "_ingested_at"},
    "invoices": {"issue_date", "due_date", "paid_on_date", "_ingested_at"},
}

DECIMAL_FIELDS: dict[str, set[str]] = {
    "customers": set(),
    "contacts": set(),
    "invoices": {
        "exchange_rate",
        "total_discount",
        "sub_total",
        "total_tax_amount",
        "total_amount",
        "balance",
    },
}

UNIQUE_KEY_COLUMNS = ("_company_id", "_source_system", "_source_record_id")


def target_mid_table(mid_table: str) -> str:
    if mid_table not in MID_TABLE_COLUMNS:
        raise ValueError(f"Unsupported mid table: {mid_table}")
    return f"mid_{mid_table}"


def parse_iso_datetime(value: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"true", "1", "t", "yes"}:
        return True
    if normalized in {"false", "0", "f", "no"}:
        return False
    raise ValueError(f"Invalid boolean value: {value!r}")


def parse_mid_row(mid_table: str, row: dict[str, str]) -> dict[str, Any]:
    if mid_table not in MID_TABLE_COLUMNS:
        raise ValueError(f"Unsupported mid table: {mid_table}")

    parsed: dict[str, Any] = {}
    for column in MID_TABLE_COLUMNS[mid_table]:
        raw_value = row.get(column, "")
        value = raw_value.strip() if isinstance(raw_value, str) else raw_value
        if value == "":
            parsed[column] = DEFAULT_VALUES[mid_table].get(column)
            continue

        if column in BOOLEAN_FIELDS[mid_table]:
            parsed[column] = parse_bool(value)
        elif column in DATETIME_FIELDS[mid_table]:
            parsed[column] = parse_iso_datetime(value)
        elif column in DECIMAL_FIELDS[mid_table]:
            parsed[column] = Decimal(value)
        elif column in JSON_FIELDS[mid_table]:
            import json

            parsed[column] = json.loads(value)
        else:
            parsed[column] = value

    return parsed


def read_mid_csv(mid_table: str, path: Path) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"CSV has no header: {path}")
        missing = [c for c in MID_TABLE_COLUMNS[mid_table] if c not in reader.fieldnames]
        if missing:
            raise ValueError(f"CSV missing required columns for {mid_table}: {missing}")
        return [parse_mid_row(mid_table, row) for row in reader]


def batch_context(
    mid_table: str,
    rows: list[dict[str, Any]],
    *,
    source_input: Path,
    mapped_csv: Path,
    sync_type: str,
) -> dict[str, Any]:
    first = rows[0] if rows else {}
    return {
        "company_id": first.get("_company_id") or "unknown",
        "source_system": first.get("_source_system") or "unknown",
        "entity_name": mid_table,
        "sync_type": sync_type,
        "mapping_version": first.get("_mapping_version") or "unknown",
        "source_file": first.get("_source_file") or source_input.name,
        "source_path": str(source_input),
        "status": "running",
        "row_count": len(rows),
        "metadata": {
            "mapped_csv": str(mapped_csv),
            "loader": "load_mid_from_mapper.py",
        },
    }


def create_load_batch(cur, context: dict[str, Any]) -> int:
    params = {**context, "metadata": Jsonb(context["metadata"])}
    cur.execute(
        """
        insert into public.ingestion_load_batches (
          company_id,
          source_system,
          entity_name,
          sync_type,
          mapping_version,
          source_file,
          source_path,
          status,
          row_count,
          metadata
        )
        values (
          %(company_id)s,
          %(source_system)s,
          %(entity_name)s,
          %(sync_type)s,
          %(mapping_version)s,
          %(source_file)s,
          %(source_path)s,
          %(status)s,
          %(row_count)s,
          %(metadata)s
        )
        returning id
        """,
        params,
    )
    return cur.fetchone()[0]


def log_validation_failure(
    cur,
    *,
    load_batch_id: int,
    company_id: str,
    entity_name: str,
    source_system: str,
    source_record_id: str | None,
    row_number: int,
    row_hash: str | None,
    error_code: str,
    error_message: str,
    raw_row: dict[str, Any],
) -> None:
    cur.execute(
        """
        insert into public.ingestion_validation_failures (
          load_batch_id,
          company_id,
          entity_name,
          source_system,
          source_record_id,
          row_number,
          row_hash,
          error_code,
          error_message,
          raw_row
        )
        values (
          %(load_batch_id)s,
          %(company_id)s,
          %(entity_name)s,
          %(source_system)s,
          %(source_record_id)s,
          %(row_number)s,
          %(row_hash)s,
          %(error_code)s,
          %(error_message)s,
          %(raw_row)s
        )
        """,
        {
            "load_batch_id": load_batch_id,
            "company_id": company_id,
            "entity_name": entity_name,
            "source_system": source_system,
            "source_record_id": source_record_id,
            "row_number": row_number,
            "row_hash": row_hash,
            "error_code": error_code,
            "error_message": error_message,
            "raw_row": Jsonb(raw_row),
        },
    )


def upsert_mid_rows(cur, mid_table: str, load_batch_id: int, rows: list[dict[str, Any]]) -> tuple[int, int]:
    if not rows:
        return (0, 0)

    data_columns = MID_TABLE_COLUMNS[mid_table]
    insert_columns = ["load_batch_id", *data_columns]
    update_columns = ["load_batch_id", *data_columns]
    update_assignments = [
        sql.SQL("{} = EXCLUDED.{}").format(sql.Identifier(column), sql.Identifier(column))
        for column in update_columns
    ]
    update_assignments.append(sql.SQL("updated_at = now()"))

    query = sql.SQL(
        """
        insert into public.{table} ({columns})
        values ({values})
        on conflict ({conflict_columns})
        do update set {updates}
        returning (xmax = 0) as inserted
        """
    ).format(
        table=sql.Identifier(target_mid_table(mid_table)),
        columns=sql.SQL(", ").join(sql.Identifier(col) for col in insert_columns),
        values=sql.SQL(", ").join(sql.Placeholder(col) for col in insert_columns),
        conflict_columns=sql.SQL(", ").join(sql.Identifier(col) for col in UNIQUE_KEY_COLUMNS),
        updates=sql.SQL(", ").join(update_assignments),
    )

    inserted = 0
    updated = 0
    for row in rows:
        params = {"load_batch_id": load_batch_id, **row}
        for column in JSON_FIELDS[mid_table]:
            if column in params and params[column] is not None:
                params[column] = Jsonb(params[column])
        cur.execute(query, params)
        was_inserted = cur.fetchone()[0]
        if was_inserted:
            inserted += 1
        else:
            updated += 1
    return (inserted, updated)


def complete_load_batch(
    cur,
    *,
    load_batch_id: int,
    status: str,
    inserted_count: int,
    updated_count: int,
    failed_count: int,
    metadata: dict[str, Any] | None = None,
) -> None:
    metadata_patch = Jsonb(metadata or {})
    cur.execute(
        """
        update public.ingestion_load_batches
        set
          status = %(status)s,
          inserted_count = %(inserted_count)s,
          updated_count = %(updated_count)s,
          failed_count = %(failed_count)s,
          metadata = coalesce(metadata, '{}'::jsonb) || %(metadata)s,
          completed_at = now()
        where id = %(load_batch_id)s
        """,
        {
            "status": status,
            "inserted_count": inserted_count,
            "updated_count": updated_count,
            "failed_count": failed_count,
            "metadata": metadata_patch,
            "load_batch_id": load_batch_id,
        },
    )
