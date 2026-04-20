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
        elif row.get("phone_numbers"):
            phone_numbers = self._optional_json(row.get("phone_numbers"), default=[])
        addresses = self._optional_json(row.get("addresses"), default=[])
        email_addresses = self._optional_json(row.get("email_addresses"), default=[])
        customer = ContactRecord(
            id=self._required_str(row, "external_id", "id"),
            remote_id=self._first_present(row, "_source_record_id", "remote_id"),
            name=self._optional_str(row.get("name")),
            email_address=self._optional_str(row.get("email_address")) or self._first_email(email_addresses),
            email_addresses=email_addresses,
            tax_number=self._optional_str(row.get("tax_number")),
            is_customer=self._optional_bool(row.get("is_customer"), default=True),
            is_supplier=self._optional_bool(row.get("is_supplier"), default=False),
            status=self._optional_str(row.get("status")),
            currency=self._optional_str(row.get("currency")),
            remote_updated_at=self._optional_datetime(row.get("remote_updated_at")),
            remote_was_deleted=self._optional_bool(
                row.get("remote_was_deleted"), default=False
            ),
            company=self._first_present(row, "_company_id", "company"),
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

    def _first_email(self, email_addresses: list[dict[str, Any]]) -> str | None:
        if not email_addresses:
            return None
        first = email_addresses[0]
        if not isinstance(first, dict):
            return None
        email_value = first.get("email_address")
        if not email_value:
            return None
        return str(email_value)
