from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from typing import Any

from erp_data_ingestion.models import ContactRecord


class ContactV1Serializer:
    def serialize_row(self, row: dict[str, str]) -> dict[str, Any]:
        first_name = self._optional_str(row.get("first_name"))
        last_name = self._optional_str(row.get("last_name"))
        full_name = " ".join(
            part for part in [first_name or "", last_name or ""] if part
        ).strip() or None
        email_addresses = self._optional_json(row.get("email_addresses"), default=[])
        phone_numbers = self._optional_json(row.get("phone_numbers"), default=[])
        addresses = self._optional_json(row.get("addresses"), default=[])
        contact = ContactRecord(
            id=row["external_id"],
            remote_id=row.get("_source_record_id") or row["external_id"],
            name=full_name,
            first_name=first_name,
            last_name=last_name,
            email_address=self._first_email(email_addresses),
            email_addresses=email_addresses,
            is_customer=True,
            is_supplier=False,
            account_external_id=self._optional_str(row.get("account_external_id")),
            company=self._optional_str(row.get("account_external_id")),
            addresses=addresses,
            phone_numbers=phone_numbers,
            remote_created_at=self._optional_datetime(row.get("remote_created_at")),
            remote_was_deleted=self._optional_bool(row.get("remote_was_deleted")),
        )
        return self._serialize_record(contact)

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
