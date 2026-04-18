from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Any

from erp_data_ingestion.models import ContactRecord


class ContactV1Serializer:
    def serialize_row(self, row: dict[str, str]) -> dict[str, Any]:
        contact = ContactRecord(
            id=row["id"],
            remote_id=self._optional_str(row.get("remote_id")),
            name=self._optional_str(row.get("name")),
            email_address=self._optional_str(row.get("email_address")),
            tax_number=self._optional_str(row.get("tax_number")),
            is_customer=self._optional_bool(row.get("is_customer")),
            is_supplier=self._optional_bool(row.get("is_supplier")),
            status=self._optional_str(row.get("status")),
            currency=self._optional_str(row.get("currency")),
            remote_updated_at=self._optional_datetime(row.get("remote_updated_at")),
            remote_was_deleted=self._optional_bool(row.get("remote_was_deleted")),
            company=self._optional_str(row.get("company")),
        )
        return self._serialize_record(contact)

    def _serialize_record(self, record: Any) -> dict[str, Any]:
        payload = asdict(record)
        for key, value in list(payload.items()):
            if isinstance(value, datetime):
                payload[key] = value.isoformat()
            elif value == {} or value == []:
                payload[key] = None
        return payload

    def _optional_str(self, value: Any) -> str | None:
        if value in (None, ""):
            return None
        return str(value)

    def _optional_datetime(self, value: Any) -> datetime | None:
        if value in (None, ""):
            return None
        return datetime.fromisoformat(str(value))

    def _optional_bool(self, value: Any) -> bool:
        if value in (None, "", False):
            return False
        if value is True:
            return True
        lowered = str(value).strip().lower()
        return lowered in {"1", "true", "yes", "y"}
