import json
from datetime import date

import pyarrow.parquet as pq
import pytest

from erp_data_ingestion.phase4 import Phase4Transformer


def test_transformer_writes_invoice_parquet_and_run_metadata(tmp_path) -> None:
    input_csv = tmp_path / "company_123_invoice_initial_20260418_run-1.csv"
    input_csv.write_text(
        "\n".join(
            [
                "external_id,number,contact_external_id,issue_date,due_date,currency,sub_total,total_tax_amount,total_amount,balance,status,remote_was_deleted,_source_record_id,_company_id",
                "inv_internal_1,INV-001,contact_123,2026-04-18T00:00:00Z,2026-04-30T00:00:00Z,USD,100.0,5.0,105.0,25.0,OPEN,false,src_inv_1,company_123",
            ]
        ),
        encoding="utf-8",
    )

    transformer = Phase4Transformer(schema_version="invoice.v1")

    result = transformer.transform_midlayer_csv(
        input_csv=input_csv,
        output_root=tmp_path / "lake",
        table="invoice",
        company_id="company_123",
        sync_type="initial",
        run_id="run-1",
        logical_date=date(2026, 4, 18),
    )

    assert result.row_count == 1
    assert result.table == "invoice"
    assert result.schema_version == "invoice.v1"
    assert result.output_path.name.endswith(".parquet")

    parquet_table = pq.read_table(result.output_path)
    rows = parquet_table.to_pylist()

    assert rows[0]["number"] == "INV-001"
    assert rows[0]["currency"] == "USD"
    assert rows[0]["total_amount"] == 105.0
    assert result.validation_summary["invalid_rows"] == 0
    assert result.manifest_path.name == "manifest.json"

    manifest = json.loads(result.manifest_path.read_text())
    assert manifest["run_id"] == "run-1"
    assert manifest["table"] == "invoice"
    assert manifest["row_count"] == 1
    assert manifest["validation_summary"]["invalid_rows"] == 0


def test_transformer_builds_partitioned_lake_path(tmp_path) -> None:
    transformer = Phase4Transformer(schema_version="contact.v1")

    path = transformer.build_output_path(
        output_root=tmp_path / "lake",
        company_id="company_123",
        table="contact",
        sync_type="delta",
        run_id="run-9",
        logical_date=date(2026, 4, 18),
    )

    assert path.as_posix().endswith(
        "company_id=company_123/table=contact/sync_type=delta/date=2026-04-18/run_id=run-9/contact.parquet"
    )


def test_transformer_writes_contact_parquet_and_emits_completion_telemetry(tmp_path) -> None:
    input_csv = tmp_path / "company_123_contact_delta_20260418_run-9.csv"
    input_csv.write_text(
        "\n".join(
            [
                "external_id,first_name,last_name,account_external_id,email_addresses,phone_numbers,addresses,remote_created_at,remote_was_deleted,_source_record_id",
                'contact_internal_1,Alice,Ng,cus_acme_001,"[{""email_address"":""billing@acme.test""}]","[{""phone_number"":""+1-415-555-0101""}]","[{""address_type"":""PRIMARY"",""full_address"":""100 Market St""}]",2026-04-10T09:00:00Z,false,src_contact_1',
            ]
        ),
        encoding="utf-8",
    )

    transformer = Phase4Transformer(schema_version="contact.v1")

    result = transformer.transform_midlayer_csv(
        input_csv=input_csv,
        output_root=tmp_path / "lake",
        table="contact",
        company_id="company_123",
        sync_type="delta",
        run_id="run-9",
        logical_date=date(2026, 4, 18),
    )

    parquet_table = pq.read_table(result.output_path)
    rows = parquet_table.to_pylist()

    assert rows[0]["name"] == "Alice Ng"
    assert rows[0]["is_customer"] is True
    assert result.run_metadata.run_id == "run-9"
    assert result.run_metadata.table == "contact"
    assert result.run_metadata.row_count == 1
    assert result.telemetry_events[0].event_name == "phase4.transform.completed"
    assert result.telemetry_events[0].attributes["table"] == "contact"


def test_transformer_fails_fast_on_invalid_contact_rows(tmp_path) -> None:
    input_csv = tmp_path / "company_123_contact_delta_20260418_run-10.csv"
    input_csv.write_text(
        "\n".join(
            [
                "external_id,first_name,last_name,account_external_id,email_addresses,phone_numbers,addresses,remote_created_at,remote_was_deleted,_source_record_id",
                'contact_internal_1,Alice,Ng,cus_acme_001,"[{""email_address"":""billing@acme.test""}]","[{""phone_number"":""+1-415-555-0101""}]","[{""address_type"":""PRIMARY"",""full_address"":""100 Market St""}]",2026-04-10T09:00:00Z,false,src_contact_1',
                'contact_internal_2,Bad,Contact,cus_acme_002,not-json,"[{""phone_number"":""+1-415-555-0102""}]","[{""address_type"":""PRIMARY"",""full_address"":""200 Main St""}]",2026-04-10T09:00:00Z,false,src_contact_2',
            ]
        ),
        encoding="utf-8",
    )

    transformer = Phase4Transformer(schema_version="contact.v1")

    with pytest.raises(ValueError):
        transformer.transform_midlayer_csv(
            input_csv=input_csv,
            output_root=tmp_path / "lake",
            table="contact",
            company_id="company_123",
            sync_type="delta",
            run_id="run-10",
            logical_date=date(2026, 4, 18),
        )

    assert not (tmp_path / "lake").exists()


def test_transformer_writes_customer_rows_as_contact_parquet(tmp_path) -> None:
    input_csv = tmp_path / "acme-co_customers_initial_20260418.csv"
    input_csv.write_text(
        "\n".join(
            [
                "external_id,name,is_supplier,is_customer,email_address,tax_number,status,currency,remote_updated_at,phone_number,addresses,remote_was_deleted,_unmapped,_source_system,_source_record_id,_company_id,_ingested_at,_source_file,_mapping_version,_row_hash",
                'cus_acme_001,Acme Holdings,false,true,finance@acme.example,TAX-ACME-001,ACTIVE,USD,2026-04-18T08:00:00Z,+1-415-555-0100,"[{""address_type"":""BILLING"",""full_address"":""100 Market St""}]",false,{},stripe,cus_001,acme-co,2026-04-18T08:00:00Z,seeds/demo.csv,stripe.customer@0.1.0,hash-customer-001',
            ]
        ),
        encoding="utf-8",
    )

    transformer = Phase4Transformer(schema_version="customer.v1")
    result = transformer.transform_midlayer_csv(
        input_csv=input_csv,
        output_root=tmp_path / "lake",
        table="customer",
        company_id="acme-co",
        sync_type="initial",
        run_id="run-1",
        logical_date=date(2026, 4, 18),
    )

    rows = pq.read_table(result.output_path).to_pylist()
    assert rows[0]["id"] == "cus_acme_001"
    assert rows[0]["is_customer"] is True
    assert rows[0]["company"] == "acme-co"
    assert result.table == "customer"
