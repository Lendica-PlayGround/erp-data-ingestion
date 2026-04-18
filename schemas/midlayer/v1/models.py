"""Pydantic v2 models mirroring the mid-layer v1 JSON Schemas.

The field order here is the canonical CSV header order for each table
(`schema_field_order()`). JSON Schemas in `schemas/midlayer/v1/*.schema.json`
remain the public contract; these models exist for runtime validation and
for authoritative header ordering.
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


class _MidLayerBase(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    _unmapped: Optional[str] = None  # minified JSON string
    # Metadata (set by the mapper/writer, required on every row)
    _source_system: str
    _source_record_id: str
    _company_id: str
    _ingested_at: datetime
    _source_file: str
    _mapping_version: str
    _row_hash: str


class Invoice(BaseModel):
    model_config = ConfigDict(extra="forbid")

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
    _unmapped: Optional[str] = None
    _source_system: str = ""
    _source_record_id: str = ""
    _company_id: str = ""
    _ingested_at: Optional[datetime] = None
    _source_file: str = ""
    _mapping_version: str = ""
    _row_hash: str = ""


class Customer(BaseModel):
    model_config = ConfigDict(extra="forbid")

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
    _unmapped: Optional[str] = None
    _source_system: str = ""
    _source_record_id: str = ""
    _company_id: str = ""
    _ingested_at: Optional[datetime] = None
    _source_file: str = ""
    _mapping_version: str = ""
    _row_hash: str = ""


class Contact(BaseModel):
    model_config = ConfigDict(extra="forbid")

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
    _unmapped: Optional[str] = None
    _source_system: str = ""
    _source_record_id: str = ""
    _company_id: str = ""
    _ingested_at: Optional[datetime] = None
    _source_file: str = ""
    _mapping_version: str = ""
    _row_hash: str = ""


# Canonical CSV header order per table: public fields, then _unmapped, then metadata.
# We enumerate explicitly rather than using `model_fields` so that the order is
# stable against future field additions.
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

SCHEMA_VERSION = "v1"
