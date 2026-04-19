"""Mid-layer v1 column order and JSON Schema snippets for prompts.

We **do not** import ``midlayer.v1.models`` here: that pulls in Pydantic models with
``EmailStr``, which requires ``email-validator``. The Phase 2 backend venv often does
not have it installed, and the handshake CLI must run under ``sys.executable`` from
that venv. Keep the lists below in sync with ``midlayer/v1/models.py`` ``TABLE_COLUMNS``.
"""

from __future__ import annotations

import json
from pathlib import Path

# Mirrors midlayer.v1.models.TABLE_COLUMNS (CSV header order).
_INVOICE_COLUMNS: list[str] = [
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
]

_CUSTOMER_COLUMNS: list[str] = [
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
]

_CONTACT_COLUMNS: list[str] = [
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
]

_TABLE_COLUMNS: dict[str, list[str]] = {
    "invoices": _INVOICE_COLUMNS,
    "customers": _CUSTOMER_COLUMNS,
    "contacts": _CONTACT_COLUMNS,
}


def table_columns() -> dict[str, list[str]]:
    return {k: list(v) for k, v in _TABLE_COLUMNS.items()}


def schema_summary_json(midlayer_v1: Path, table: str) -> str:
    """Subset of JSON Schema `properties` for LLM context (types, descriptions, enums)."""
    fname = {"invoices": "invoice", "customers": "customer", "contacts": "contact"}[table]
    path = midlayer_v1 / f"{fname}.schema.json"
    if not path.is_file():
        raise FileNotFoundError(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    props = data.get("properties") or {}
    slim: dict[str, object] = {}
    for k, v in props.items():
        if not isinstance(v, dict):
            continue
        entry: dict[str, object] = {}
        if "type" in v:
            entry["type"] = v["type"]
        if v.get("description"):
            entry["description"] = v["description"]
        if v.get("enum"):
            entry["enum"] = v["enum"]
        if v.get("format"):
            entry["format"] = v["format"]
        if v.get("pattern"):
            entry["pattern"] = v["pattern"]
        slim[k] = entry
    return json.dumps(slim, indent=2, ensure_ascii=False)
