from erp_data_ingestion.serializers import get_serializer


def test_invoice_v1_serializer_maps_midlayer_row_to_canonical_invoice_payload() -> None:
    serializer = get_serializer(table="invoice", schema_version="invoice.v1")

    payload = serializer.serialize_row(
        {
            "external_id": "inv_internal_1",
            "_source_record_id": "src_inv_1",
            "number": "INV-001",
            "contact_external_id": "contact_123",
            "_company_id": "company_123",
            "issue_date": "2026-04-18T00:00:00Z",
            "currency": "USD",
            "sub_total": "100.0",
            "total_tax_amount": "5.0",
            "total_amount": "105.0",
            "balance": "25.0",
            "status": "OPEN",
            "remote_was_deleted": "false",
        }
    )

    assert payload["id"] == "inv_internal_1"
    assert payload["number"] == "INV-001"
    assert payload["currency"] == "USD"
    assert payload["total_amount"] == 105.0
    assert payload["issue_date"] == "2026-04-18T00:00:00Z"
    assert payload["contact"] == "contact_123"
    assert payload["company"] == "company_123"


def test_contact_v1_serializer_maps_crm_contact_row_to_canonical_contact_payload() -> None:
    serializer = get_serializer(table="contact", schema_version="contact.v1")

    payload = serializer.serialize_row(
        {
            "external_id": "contact_acme_001",
            "_source_record_id": "src_contact_1",
            "first_name": "Alice",
            "last_name": "Ng",
            "account_external_id": "cus_acme_001",
            "email_addresses": '[{"email_address":"alice.ng@acme.example","email_address_type":"WORK"}]',
            "phone_numbers": '[{"phone_number":"+1-415-555-0101","phone_number_type":"WORK"}]',
            "addresses": '[{"address_type":"PRIMARY","full_address":"100 Market St"}]',
            "last_activity_at": "2026-04-18T07:30:00Z",
            "remote_created_at": "2026-04-10T09:00:00Z",
            "remote_was_deleted": "false",
        }
    )

    assert payload["id"] == "contact_acme_001"
    assert payload["first_name"] == "Alice"
    assert payload["last_name"] == "Ng"
    assert payload["account_external_id"] == "cus_acme_001"
    assert payload["name"] == "Alice Ng"
    assert payload["email_address"] == "alice.ng@acme.example"
    assert payload["phone_numbers"][0]["phone_number"] == "+1-415-555-0101"
    assert payload["is_customer"] is True
    assert payload["is_supplier"] is False


def test_customer_v1_serializer_maps_midlayer_customer_row_to_canonical_contact_payload() -> None:
    serializer = get_serializer(table="customer", schema_version="customer.v1")

    payload = serializer.serialize_row(
        {
            "external_id": "cus_acme_001",
            "_source_record_id": "src_customer_1",
            "name": "Acme Holdings",
            "is_supplier": "false",
            "is_customer": "true",
            "email_address": "finance@acme.example",
            "tax_number": "TAX-ACME-001",
            "status": "ACTIVE",
            "currency": "USD",
            "remote_updated_at": "2026-04-18T08:00:00Z",
            "phone_number": "+1-415-555-0100",
            "addresses": '[{"address_type":"BILLING","full_address":"100 Market St"}]',
            "remote_was_deleted": "false",
            "_company_id": "acme-co",
        }
    )

    assert payload["id"] == "cus_acme_001"
    assert payload["name"] == "Acme Holdings"
    assert payload["is_customer"] is True
    assert payload["is_supplier"] is False
    assert payload["phone_numbers"][0]["phone_number"] == "+1-415-555-0100"
    assert payload["company"] == "acme-co"


def test_serializer_registry_rejects_mismatched_schema_version() -> None:
    try:
        get_serializer(table="invoice", schema_version="contact.v1")
    except ValueError as exc:
        assert "schema_version" in str(exc)
    else:
        raise AssertionError("expected mismatched schema version to raise ValueError")
