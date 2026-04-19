"""Pydantic v2 models mirroring the mid-layer v1 JSON Schemas.

Two important details:

1. The field order here is the canonical CSV header order for each table
   (see ``INVOICE_COLUMNS`` / ``CUSTOMER_COLUMNS`` / ``CONTACT_COLUMNS``).
2. The metadata columns (``_source_system``, ``_row_hash``, …) use Python
   attribute names **without** the leading underscore and declare the
   underscore-prefixed CSV/JSON column name via ``Field(alias=...)``. In
   Pydantic v2 a leading-underscore identifier is treated as a private
   attribute and is silently skipped by validation and serialization, which
   would quietly break the contract. Using aliases lets us validate and
   round-trip the on-the-wire names while keeping the Python attributes
   ergonomic.

Construct models with either keyword (``source_system=...``) or alias
(``**{"_source_system": ...}``) forms; dump with ``model_dump(by_alias=True)``
or ``model_dump_json(by_alias=True)`` to get the canonical column names back.
JSON Schemas in ``midlayer-schema-guide/midlayer/v1/*.schema.json`` remain the
public contract; these models exist for runtime validation and for
authoritative header ordering.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


InvoiceStatus = Literal[
    "DRAFT",
    "OPEN",
    "PAID",
    "UNCOLLECTIBLE",
    "VOID",
    "PARTIALLY_PAID",
    "SUBMITTED",
]
InvoiceType = Literal["ACCOUNTS_RECEIVABLE", "ACCOUNTS_PAYABLE"]
CustomerStatus = Literal["ACTIVE", "ARCHIVED"]


_MIDLAYER_MODEL_CONFIG = ConfigDict(
    extra="forbid",
    populate_by_name=True,
    str_strip_whitespace=False,
)


class Invoice(BaseModel):
    model_config = _MIDLAYER_MODEL_CONFIG

    external_id: str
    type: Optional[InvoiceType] = None
    number: Optional[str] = None
    contact_external_id: Optional[str] = None
    issue_date: Optional[datetime] = None
    due_date: Optional[datetime] = None
    paid_on_date: Optional[datetime] = None
    memo: Optional[str] = None
    currency: Optional[str] = Field(default=None, pattern=r"^[A-Z]{3}$")
    exchange_rate: Optional[str] = None
    total_discount: Optional[str] = None
    sub_total: Optional[str] = None
    total_tax_amount: Optional[str] = None
    total_amount: Optional[str] = None
    balance: Optional[str] = None
    status: Optional[InvoiceStatus] = None
    remote_was_deleted: bool = False

    unmapped: Optional[str] = Field(default=None, alias="_unmapped")
    source_system: str = Field(alias="_source_system")
    source_record_id: str = Field(alias="_source_record_id")
    company_id: str = Field(alias="_company_id")
    ingested_at: datetime = Field(alias="_ingested_at")
    source_file: str = Field(alias="_source_file")
    mapping_version: str = Field(alias="_mapping_version")
    row_hash: str = Field(alias="_row_hash")


class Customer(BaseModel):
    model_config = _MIDLAYER_MODEL_CONFIG

    external_id: str
    name: Optional[str] = None
    is_supplier: bool = False
    is_customer: bool = True
    email_address: Optional[EmailStr] = None
    tax_number: Optional[str] = None
    status: Optional[CustomerStatus] = None
    currency: Optional[str] = Field(default=None, pattern=r"^[A-Z]{3}$")
    remote_updated_at: Optional[datetime] = None
    phone_number: Optional[str] = None
    addresses: Optional[str] = None
    remote_was_deleted: bool = False

    unmapped: Optional[str] = Field(default=None, alias="_unmapped")
    source_system: str = Field(alias="_source_system")
    source_record_id: str = Field(alias="_source_record_id")
    company_id: str = Field(alias="_company_id")
    ingested_at: datetime = Field(alias="_ingested_at")
    source_file: str = Field(alias="_source_file")
    mapping_version: str = Field(alias="_mapping_version")
    row_hash: str = Field(alias="_row_hash")


class Contact(BaseModel):
    model_config = _MIDLAYER_MODEL_CONFIG

    external_id: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    account_external_id: Optional[str] = None
    addresses: Optional[str] = None
    email_addresses: Optional[str] = None
    phone_numbers: Optional[str] = None
    last_activity_at: Optional[datetime] = None
    remote_created_at: Optional[datetime] = None
    remote_was_deleted: bool = False

    unmapped: Optional[str] = Field(default=None, alias="_unmapped")
    source_system: str = Field(alias="_source_system")
    source_record_id: str = Field(alias="_source_record_id")
    company_id: str = Field(alias="_company_id")
    ingested_at: datetime = Field(alias="_ingested_at")
    source_file: str = Field(alias="_source_file")
    mapping_version: str = Field(alias="_mapping_version")
    row_hash: str = Field(alias="_row_hash")


# Canonical CSV header order per table: public fields, then _unmapped, then metadata.
# We enumerate explicitly rather than using `model_fields` so that the order is
# stable against future field additions. These names match the CSV/JSON
# aliases (leading-underscore for metadata), NOT the Python attribute names.
INVOICE_COLUMNS: list[str] = [
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

CUSTOMER_COLUMNS: list[str] = [
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

CONTACT_COLUMNS: list[str] = [
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

TABLE_COLUMNS: dict[str, list[str]] = {
    "invoices": INVOICE_COLUMNS,
    "customers": CUSTOMER_COLUMNS,
    "contacts": CONTACT_COLUMNS,
}

TABLE_MODELS: dict[str, type[BaseModel]] = {
    "invoices": Invoice,
    "customers": Customer,
    "contacts": Contact,
}

# Columns that participate in `_row_hash` (mapped public fields only — never
# `_unmapped` or metadata). Order is documentation; the hash itself sorts keys
# alphabetically, see schema guide §7.1.
ROW_HASH_COLUMNS: dict[str, list[str]] = {
    table: [c for c in cols if not c.startswith("_") and c != "remote_was_deleted"]
    # `remote_was_deleted` is intentionally included in the hash so tombstone
    # flips produce a new hash and propagate through delta dedupe.
    + (["remote_was_deleted"] if "remote_was_deleted" in cols else [])
    for table, cols in TABLE_COLUMNS.items()
}

SCHEMA_VERSION = "v1"
