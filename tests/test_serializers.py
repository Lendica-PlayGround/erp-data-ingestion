from erp_data_ingestion.serializers import get_serializer


def test_invoice_v1_serializer_maps_midlayer_row_to_canonical_invoice_payload() -> None:
    serializer = get_serializer(table="invoice", schema_version="invoice.v1")

    payload = serializer.serialize_row(
        {
            "id": "inv_internal_1",
            "remote_id": "src_inv_1",
            "number": "INV-001",
            "contact": "contact_123",
            "company": "company_123",
            "issue_date": "2026-04-18T00:00:00+00:00",
            "currency": "USD",
            "sub_total": "100.0",
            "total_tax_amount": "5.0",
            "total_amount": "105.0",
            "balance": "25.0",
            "status": "OPEN",
        }
    )

    assert payload["id"] == "inv_internal_1"
    assert payload["number"] == "INV-001"
    assert payload["currency"] == "USD"
    assert payload["total_amount"] == 105.0
    assert payload["issue_date"] == "2026-04-18T00:00:00+00:00"


def test_contact_v1_serializer_maps_midlayer_row_to_canonical_contact_payload() -> None:
    serializer = get_serializer(table="contact", schema_version="contact.v1")

    payload = serializer.serialize_row(
        {
            "id": "contact_internal_1",
            "remote_id": "src_contact_1",
            "name": "Acme Corp",
            "email_address": "billing@acme.test",
            "is_customer": "true",
            "is_supplier": "false",
            "status": "ACTIVE",
            "currency": "USD",
            "company": "company_123",
        }
    )

    assert payload["id"] == "contact_internal_1"
    assert payload["name"] == "Acme Corp"
    assert payload["is_customer"] is True
    assert payload["currency"] == "USD"


def test_serializer_registry_rejects_mismatched_schema_version() -> None:
    try:
        get_serializer(table="invoice", schema_version="contact.v1")
    except ValueError as exc:
        assert "schema_version" in str(exc)
    else:
        raise AssertionError("expected mismatched schema version to raise ValueError")
