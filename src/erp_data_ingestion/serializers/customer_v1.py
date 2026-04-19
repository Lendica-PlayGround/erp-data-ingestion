from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from typing import Any

from erp_data_ingestion.models import ContactRecord


class CustomerV1Serializer:
    def serialize_row(self, row: dict[str, str]) -> dict[str, Any]:
        phone_numbers = []
        if row.get("phone_number"):
            phone_numbers.append(
                {
                    "phone_number": row["phone_number"],
                    "phone_number_type": "WORK",
                }
            )
        addresses = self._optional_json(row.get("addresses"), default=[])
        customer = ContactRecord(
            id=row["external_id"],
            remote_id=row.get("_source_record_id") or row["external_id"],
            name=self._optional_str(row.get("name")),
            email_address=self._optional_str(row.get("email_address")),
            email_addresses=[],
            tax_number=self._optional_str(row.get("tax_number")),
            is_customer=self._optional_bool(row.get("is_customer"), default=True),
            is_supplier=self._optional_bool(row.get("is_supplier"), default=False),
            status=self._optional_str(row.get("status")),
            currency=self._optional_str(row.get("currency")),
            remote_updated_at=self._optional_datetime(row.get("remote_updated_at")),
            remote_was_deleted=self._optional_bool(
                row.get("remote_was_deleted"), default=False
            ),
            company=row.get("_company_id"),
            addresses=addresses,
            phone_numbers=phone_numbers,
        )
        return self._serialize_record(customer)

    def _serialize_record(self, record: Any) -> dict[str, Any]:
        payload = asdict(record)
        for key, value in list(payload.items()):
            if isinstance(value, datetime):
                payload[key] = value.isoformat().replace("+00:00", "Z")
            elif value == {} or value == []:
                payload[key] = None
        return payload

    def _optional_str(self, value: Any) -> str | None:
        if value in (None, ""):
            return None
        return str(value)

    def _optional_bool(self, value: Any, *, default: bool) -> bool:
        if value in (None, ""):
            return default
        lowered = str(value).strip().lower()
        return lowered in {"1", "true", "yes", "y"}

    def _optional_datetime(self, value: Any) -> datetime | None:
        if value in (None, ""):
            return None
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))

    def _optional_json(
        self, value: Any, *, default: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        if value in (None, ""):
            return list(default)
        return json.loads(str(value))
