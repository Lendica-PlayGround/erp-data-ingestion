from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Any

from erp_data_ingestion.models import InvoiceRecord


class InvoiceV1Serializer:
    def serialize_row(self, row: dict[str, str]) -> dict[str, Any]:
        invoice = InvoiceRecord(
            id=self._required_str(row, "external_id", "id"),
            remote_id=self._first_present(row, "_source_record_id", "remote_id"),
            number=self._optional_str(row.get("number")),
            contact=self._first_present(row, "contact_external_id", "contact"),
            company=self._first_present(row, "_company_id", "company"),
            issue_date=self._optional_datetime(row.get("issue_date")),
            due_date=self._optional_datetime(row.get("due_date")),
            paid_on_date=self._optional_datetime(row.get("paid_on_date")),
            currency=self._optional_str(row.get("currency")),
            exchange_rate=self._optional_float(row.get("exchange_rate")),
            sub_total=self._optional_float(row.get("sub_total")),
            total_tax_amount=self._optional_float(row.get("total_tax_amount")),
            total_discount=self._optional_float(row.get("total_discount")),
            total_amount=self._optional_float(row.get("total_amount")),
            balance=self._optional_float(row.get("balance")),
            type=self._optional_str(row.get("type")),
            status=self._optional_str(row.get("status")),
            memo=self._optional_str(row.get("memo")),
            remote_updated_at=self._optional_datetime(row.get("remote_updated_at")),
            remote_was_deleted=self._optional_bool(row.get("remote_was_deleted")),
        )
        return self._serialize_record(invoice)

    def _serialize_record(self, record: Any) -> dict[str, Any]:
        payload = asdict(record)
        for key, value in list(payload.items()):
            if isinstance(value, datetime):
                payload[key] = value.isoformat().replace("+00:00", "Z")
            elif value == {} or value == []:
                payload[key] = None
        return payload

    def _required_str(self, row: dict[str, str], *keys: str) -> str:
        value = self._first_present(row, *keys)
        if value is None:
            joined = ", ".join(keys)
            raise KeyError(f"missing required field from one of: {joined}")
        return value

    def _first_present(self, row: dict[str, str], *keys: str) -> str | None:
        for key in keys:
            value = self._optional_str(row.get(key))
            if value is not None:
                return value
        return None

    def _optional_str(self, value: Any) -> str | None:
        if value in (None, ""):
            return None
        return str(value)

    def _optional_float(self, value: Any) -> float | None:
        if value in (None, ""):
            return None
        return float(value)

    def _optional_datetime(self, value: Any) -> datetime | None:
        if value in (None, ""):
            return None
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))

    def _optional_bool(self, value: Any) -> bool:
        if value in (None, "", False):
            return False
        if value is True:
            return True
        lowered = str(value).strip().lower()
        return lowered in {"1", "true", "yes", "y"}
