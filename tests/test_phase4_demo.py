from pathlib import Path

from erp_data_ingestion.phase4_demo import Phase4DemoRequest, Phase4DemoRunner


def test_demo_runner_uses_seeded_dataset_and_persists_run_state(tmp_path: Path) -> None:
    seed_root = tmp_path / "seeds"
    seed_root.mkdir()
    (seed_root / "invoice.csv").write_text(
        "id,remote_id,number,contact,company,issue_date,due_date,currency,sub_total,total_tax_amount,total_amount,balance,status\n"
        "inv_internal_1,src_inv_1,INV-001,contact_123,company_123,2026-04-19T00:00:00+00:00,2026-04-30T00:00:00+00:00,USD,100.0,5.0,105.0,25.0,OPEN\n",
        encoding="utf-8",
    )
    (seed_root / "contact.csv").write_text(
        "id,remote_id,name,email_address,is_customer,is_supplier,status,currency,company\n"
        "contact_internal_1,src_contact_1,Acme Contact,billing@acme.test,true,false,ACTIVE,USD,company_123\n",
        encoding="utf-8",
    )
    (seed_root / "customer.csv").write_text(
        "id,remote_id,name,email_address,is_customer,is_supplier,status,currency,company\n"
        "customer_internal_1,src_customer_1,Acme Customer,customer@acme.test,true,false,ACTIVE,USD,company_123\n",
        encoding="utf-8",
    )
    runner = Phase4DemoRunner(output_root=tmp_path / "runs")

    result = runner.run(
        Phase4DemoRequest(
            run_id="run-seeded",
            company_id="company_123",
            dataset="seeded",
            seed_root=seed_root,
            sync_type="initial",
        )
    )

    assert result.status == "succeeded"
    assert (tmp_path / "runs" / "run-seeded" / "run_state.json").is_file()
    assert set(result.tables) == {"invoice", "contact", "customer"}


def test_demo_runner_accepts_explicit_overrides(tmp_path: Path) -> None:
    invoice_csv = tmp_path / "invoice.csv"
    contact_csv = tmp_path / "contact.csv"
    customer_csv = tmp_path / "customer.csv"
    invoice_csv.write_text(
        "id,remote_id,number,contact,company,issue_date,due_date,currency,sub_total,total_tax_amount,total_amount,balance,status\n"
        "inv_internal_1,src_inv_1,INV-001,contact_123,company_123,2026-04-19T00:00:00+00:00,2026-04-30T00:00:00+00:00,USD,100.0,5.0,105.0,25.0,OPEN\n",
        encoding="utf-8",
    )
    contact_csv.write_text(
        "id,remote_id,name,email_address,is_customer,is_supplier,status,currency,company\n"
        "contact_internal_1,src_contact_1,Acme Contact,billing@acme.test,true,false,ACTIVE,USD,company_123\n",
        encoding="utf-8",
    )
    customer_csv.write_text(
        "id,remote_id,name,email_address,is_customer,is_supplier,status,currency,company\n"
        "customer_internal_1,src_customer_1,Acme Customer,customer@acme.test,true,false,ACTIVE,USD,company_123\n",
        encoding="utf-8",
    )

    runner = Phase4DemoRunner(output_root=tmp_path / "runs")
    result = runner.run(
        Phase4DemoRequest(
            run_id="run-overrides",
            company_id="company_123",
            dataset="custom",
            sync_type="delta",
            input_paths={
                "invoice": invoice_csv,
                "contact": contact_csv,
                "customer": customer_csv,
            },
        )
    )

    assert result.status == "succeeded"
    assert result.tables["invoice"].row_count == 1
    assert result.tables["contact"].row_count == 1
    assert result.tables["customer"].row_count == 1
