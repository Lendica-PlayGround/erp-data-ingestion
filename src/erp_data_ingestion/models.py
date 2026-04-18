from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass
class InvoiceRecord:
    id: str
    remote_id: Optional[str] = None
    number: Optional[str] = None
    contact: Optional[str] = None
    company: Optional[str] = None
    issue_date: Optional[datetime] = None
    due_date: Optional[datetime] = None
    paid_on_date: Optional[datetime] = None
    currency: Optional[str] = None
    exchange_rate: Optional[float] = None
    sub_total: Optional[float] = None
    total_tax_amount: Optional[float] = None
    total_discount: Optional[float] = None
    total_amount: Optional[float] = None
    balance: Optional[float] = None
    type: Optional[str] = None
    status: Optional[str] = None
    memo: Optional[str] = None
    remote_updated_at: Optional[datetime] = None
    remote_was_deleted: bool = False
    line_items: List[Dict[str, Any]] = field(default_factory=list)
    remote_data: List[Dict[str, Any]] = field(default_factory=list)
    remote_fields: List[Dict[str, Any]] = field(default_factory=list)
    field_mappings: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ContactRecord:
    id: str
    remote_id: Optional[str] = None
    name: Optional[str] = None
    email_address: Optional[str] = None
    tax_number: Optional[str] = None
    is_customer: Optional[bool] = None
    is_supplier: Optional[bool] = None
    status: Optional[str] = None
    currency: Optional[str] = None
    remote_updated_at: Optional[datetime] = None
    remote_was_deleted: bool = False
    company: Optional[str] = None
    addresses: List[Dict[str, Any]] = field(default_factory=list)
    phone_numbers: List[Dict[str, Any]] = field(default_factory=list)
    remote_data: List[Dict[str, Any]] = field(default_factory=list)
    remote_fields: List[Dict[str, Any]] = field(default_factory=list)
    field_mappings: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.is_customer and not self.is_supplier:
            raise ValueError("contact must be marked as customer or supplier")


@dataclass
class RunMetadataRecord:
    run_id: str
    company_id: str
    table: str
    sync_type: str
    schema_version: str
    source_path: str
    output_path: str
    row_count: int
    status: str
    validation_summary: Dict[str, int]


@dataclass
class TelemetryEvent:
    event_name: str
    attributes: Dict[str, Any] = field(default_factory=dict)
    occurred_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
