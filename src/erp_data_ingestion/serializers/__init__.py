from __future__ import annotations

from typing import Protocol

from erp_data_ingestion.serializers.contact_v1 import ContactV1Serializer
from erp_data_ingestion.serializers.customer_v1 import CustomerV1Serializer
from erp_data_ingestion.serializers.invoice_v1 import InvoiceV1Serializer


class RowSerializer(Protocol):
    def serialize_row(self, row: dict[str, str]) -> dict[str, object]:
        ...


def get_serializer(table: str, schema_version: str) -> RowSerializer:
    if table == "invoice" and schema_version == "invoice.v1":
        return InvoiceV1Serializer()
    if table == "contact" and schema_version == "contact.v1":
        return ContactV1Serializer()
    if table == "customer" and schema_version == "customer.v1":
        return CustomerV1Serializer()
    raise ValueError(
        f"unsupported serializer for table={table!r} schema_version={schema_version!r}"
    )
