from datetime import datetime, timezone

import pytest

from erp_data_ingestion.models import ContactRecord, InvoiceRecord, RunMetadataRecord


def test_invoice_record_preserves_merge_aligned_invoice_fields() -> None:
    invoice = InvoiceRecord(
        id="inv_internal_1",
        remote_id="src_inv_1",
        number="INV-001",
        contact="contact_123",
        company="company_123",
        issue_date=datetime(2026, 4, 18, tzinfo=timezone.utc),
        due_date=datetime(2026, 4, 30, tzinfo=timezone.utc),
        currency="USD",
        sub_total=100.0,
        total_tax_amount=5.0,
        total_amount=105.0,
        balance=25.0,
        line_items=[{"description": "Consulting", "total_amount": 105.0}],
    )

    assert invoice.number == "INV-001"
    assert invoice.contact == "contact_123"
    assert invoice.currency == "USD"
    assert invoice.total_amount == 105.0
    assert invoice.line_items[0]["description"] == "Consulting"


def test_contact_record_requires_customer_or_supplier_role() -> None:
    with pytest.raises(ValueError):
        ContactRecord(
            id="contact_internal_1",
            remote_id="src_contact_1",
            name="Acme Corp",
            is_customer=False,
            is_supplier=False,
        )


def test_contact_record_supports_customer_and_crm_contact_inputs() -> None:
    customer_contact = ContactRecord(
        id="cus_acme_001",
        name="Acme Holdings",
        is_customer=True,
        is_supplier=False,
        email_address="finance@acme.example",
    )
    crm_contact = ContactRecord(
        id="contact_acme_001",
        first_name="Alice",
        last_name="Ng",
        name="Alice Ng",
        account_external_id="cus_acme_001",
        email_addresses=[{"email_address": "alice.ng@acme.example"}],
        is_customer=True,
        is_supplier=False,
    )

    assert customer_contact.email_address == "finance@acme.example"
    assert crm_contact.first_name == "Alice"
    assert crm_contact.account_external_id == "cus_acme_001"
    assert crm_contact.email_addresses[0]["email_address"] == "alice.ng@acme.example"


def test_run_metadata_record_captures_control_plane_fields() -> None:
    metadata = RunMetadataRecord(
        run_id="run-42",
        company_id="company_123",
        table="invoice",
        sync_type="delta",
        schema_version="invoice.v1",
        source_path="supabase://midlayer-csv/company_123_invoice_delta.csv",
        output_path="s3://lake/company_id=company_123/table=invoice/run_id=run-42/invoice.parquet",
        row_count=10,
        status="success",
        validation_summary={"invalid_rows": 0},
    )

    assert metadata.run_id == "run-42"
    assert metadata.company_id == "company_123"
    assert metadata.status == "success"
    assert metadata.validation_summary["invalid_rows"] == 0
