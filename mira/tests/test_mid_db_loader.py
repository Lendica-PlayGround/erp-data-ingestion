from decimal import Decimal

from framework.mid_db_loader import complete_load_batch, parse_mid_row, target_mid_table
from psycopg.types.json import Jsonb


def test_target_mid_table_names():
    assert target_mid_table("customers") == "mid_customers"
    assert target_mid_table("contacts") == "mid_contacts"
    assert target_mid_table("invoices") == "mid_invoices"


def test_parse_customer_row_converts_types():
    row = {
        "external_id": "cus_123",
        "name": "Acme",
        "is_supplier": "false",
        "is_customer": "true",
        "email_address": "ops@example.com",
        "tax_number": "",
        "status": "ACTIVE",
        "currency": "USD",
        "remote_updated_at": "2026-04-19T18:00:00Z",
        "phone_number": "555-1111",
        "addresses": "",
        "remote_was_deleted": "false",
        "_unmapped": "{\"legacy\":\"x\"}",
        "_source_system": "stripe",
        "_source_record_id": "cus_123",
        "_company_id": "acme-co",
        "_ingested_at": "2026-04-19T18:05:00Z",
        "_source_file": "customers.csv",
        "_mapping_version": "v1",
        "_row_hash": "abc",
    }

    parsed = parse_mid_row("customers", row)

    assert parsed["is_supplier"] is False
    assert parsed["is_customer"] is True
    assert parsed["remote_was_deleted"] is False
    assert parsed["_unmapped"] == {"legacy": "x"}
    assert parsed["remote_updated_at"].isoformat() == "2026-04-19T18:00:00+00:00"
    assert parsed["_ingested_at"].isoformat() == "2026-04-19T18:05:00+00:00"


def test_parse_invoice_row_converts_decimals_and_nulls():
    row = {
        "external_id": "in_123",
        "type": "ACCOUNTS_RECEIVABLE",
        "number": "INV-001",
        "contact_external_id": "cus_123",
        "issue_date": "2026-04-01T00:00:00Z",
        "due_date": "2026-04-15T00:00:00Z",
        "paid_on_date": "",
        "memo": "",
        "currency": "USD",
        "exchange_rate": "1.000000",
        "total_discount": "0.0000",
        "sub_total": "100.0000",
        "total_tax_amount": "8.2500",
        "total_amount": "108.2500",
        "balance": "108.2500",
        "status": "OPEN",
        "remote_was_deleted": "false",
        "_unmapped": "",
        "_source_system": "stripe",
        "_source_record_id": "in_123",
        "_company_id": "acme-co",
        "_ingested_at": "2026-04-19T18:05:00Z",
        "_source_file": "invoices.csv",
        "_mapping_version": "v1",
        "_row_hash": "def",
    }

    parsed = parse_mid_row("invoices", row)

    assert parsed["exchange_rate"] == Decimal("1.000000")
    assert parsed["total_amount"] == Decimal("108.2500")
    assert parsed["paid_on_date"] is None
    assert parsed["_unmapped"] == {}


def test_complete_load_batch_can_store_metadata_patch():
    class FakeCursor:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict[str, object]]] = []

        def execute(self, query, params) -> None:
            self.calls.append((str(query), params))

    cur = FakeCursor()

    complete_load_batch(
        cur,
        load_batch_id=7,
        status="completed",
        inserted_count=2,
        updated_count=1,
        failed_count=0,
        metadata={
            "artifact_manifest": {"artifact_prefix": "company_id=acme/run_id=run-123/batch_id=7"},
            "run_events": [{"event_type": "load_batch_completed"}],
        },
    )

    _, params = cur.calls[0]
    assert params["load_batch_id"] == 7
    assert params["metadata"] is not None
    assert isinstance(params["metadata"], Jsonb)
