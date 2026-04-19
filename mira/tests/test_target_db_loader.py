from datetime import datetime, timezone
from decimal import Decimal

from framework.target_db_loader import (
    build_target_contact_row,
    build_target_customer_row,
    build_target_invoice_row,
    load_target_contacts,
)


def test_build_target_customer_row_maps_mid_fields() -> None:
    mid_customer = {
        "id": 1,
        "load_batch_id": 7,
        "external_id": "cus_123",
        "name": "Acme Corp",
        "is_supplier": False,
        "is_customer": True,
        "email_address": "ops@example.com",
        "tax_number": "TAX-1",
        "status": "ACTIVE",
        "currency": "USD",
        "remote_updated_at": datetime(2026, 4, 19, 12, 0, tzinfo=timezone.utc),
        "phone_number": "555-1111",
        "addresses": "[]",
        "remote_was_deleted": False,
        "_source_system": "invoiced",
        "_source_record_id": "cus_123",
        "_company_id": "acme",
    }

    target = build_target_customer_row(mid_customer)

    assert target["mid_customer_id"] == 1
    assert target["customer_external_id"] == "cus_123"
    assert target["customer_company_name"] == "Acme Corp"
    assert target["company_id"] == "acme"


def test_build_target_contact_row_links_customer_when_available() -> None:
    mid_contact = {
        "id": 2,
        "load_batch_id": 7,
        "external_id": "con_123",
        "account_external_id": "cus_123",
        "first_name": "Jane",
        "last_name": "Doe",
        "addresses": "[]",
        "email_addresses": "[]",
        "phone_numbers": "[]",
        "last_activity_at": datetime(2026, 4, 19, 12, 0, tzinfo=timezone.utc),
        "remote_created_at": datetime(2026, 4, 19, 11, 0, tzinfo=timezone.utc),
        "remote_was_deleted": False,
        "_source_system": "invoiced",
        "_source_record_id": "con_123",
        "_company_id": "acme",
    }

    target = build_target_contact_row(mid_contact, target_customer_id=9)

    assert target["mid_contact_id"] == 2
    assert target["target_customer_id"] == 9
    assert target["full_name"] == "Jane Doe"


def test_build_target_invoice_row_derives_paid_amount_and_aging() -> None:
    mid_invoice = {
        "id": 3,
        "load_batch_id": 7,
        "external_id": "inv_123",
        "number": "INV-1",
        "contact_external_id": "cus_123",
        "type": "ACCOUNTS_RECEIVABLE",
        "issue_date": datetime(2026, 4, 1, 0, 0, tzinfo=timezone.utc),
        "due_date": datetime(2026, 4, 10, 0, 0, tzinfo=timezone.utc),
        "paid_on_date": None,
        "memo": "Test",
        "currency": "USD",
        "exchange_rate": Decimal("1.0"),
        "total_discount": Decimal("0.0"),
        "sub_total": Decimal("100.0"),
        "total_tax_amount": Decimal("8.0"),
        "total_amount": Decimal("108.0"),
        "balance": Decimal("8.0"),
        "status": "OPEN",
        "remote_was_deleted": False,
        "_source_system": "invoiced",
        "_source_record_id": "inv_123",
        "_company_id": "acme",
    }

    target = build_target_invoice_row(
        mid_invoice,
        target_customer_id=9,
        today=datetime(2026, 4, 19, 0, 0, tzinfo=timezone.utc),
    )

    assert target["mid_invoice_id"] == 3
    assert target["paid_amount"] == Decimal("100.0")
    assert target["days_outstanding"] == 9
    assert target["aging_bucket"] == "1_30"


def test_load_target_contacts_only_reads_completed_batches() -> None:
    class FakeCursor:
        def __init__(self) -> None:
            self.query = ""

        def execute(self, query, params) -> None:
            self.query = str(query)

        def fetchall(self):
            return []

    cur = FakeCursor()
    load_target_contacts(cur, company_id="acme")

    assert "ingestion_load_batches" in cur.query
    assert "status = 'completed'" in cur.query
