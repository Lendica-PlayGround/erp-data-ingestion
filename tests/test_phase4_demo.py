import json
from pathlib import Path

import pytest

DEMO_CSV_FIXTURES = {
    "invoice": (
        "id,remote_id,number,contact,company,issue_date,due_date,currency,sub_total,total_tax_amount,total_amount,balance,status\n"
        "inv_internal_1,src_inv_1,INV-001,contact_internal_1,company_123,2026-04-19T00:00:00+00:00,2026-04-30T00:00:00+00:00,USD,100.0,5.0,105.0,25.0,OPEN\n"
    ),
    "contact": (
        "id,remote_id,name,email_address,is_customer,is_supplier,status,currency,company\n"
        "contact_internal_1,src_contact_1,Acme Contact,billing@acme.test,true,false,ACTIVE,USD,company_123\n"
    ),
    "customer": (
        "id,remote_id,name,email_address,is_customer,is_supplier,status,currency,company\n"
        "customer_internal_1,src_customer_1,Acme Customer,customer@acme.test,true,false,ACTIVE,USD,company_123\n"
    ),
}


def _load_phase4_demo_runner():
    try:
        from erp_data_ingestion.phase4_demo import Phase4DemoRequest, Phase4DemoRunner
    except ModuleNotFoundError as exc:
        if exc.name == "erp_data_ingestion.phase4_demo":
            pytest.fail(f"phase4_demo module missing: {exc.name}")
        raise
    return Phase4DemoRequest, Phase4DemoRunner


def _write_demo_csv(path: Path, name: str) -> None:
    path.write_text(DEMO_CSV_FIXTURES[name], encoding="utf-8")


def _build_demo_overrides(base: Path) -> dict[str, Path]:
    overrides: dict[str, Path] = {}
    for name in DEMO_CSV_FIXTURES:
        path = base / f"{name}.csv"
        _write_demo_csv(path, name)
        overrides[name] = path
    return overrides


def _read_run_state(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_demo_runner_uses_seeded_dataset_and_persists_run_state(tmp_path: Path) -> None:
    seed_root = tmp_path / "seeds"
    seed_root.mkdir()
    for name in DEMO_CSV_FIXTURES:
        _write_demo_csv(seed_root / f"{name}.csv", name)

    Phase4DemoRequest, Phase4DemoRunner = _load_phase4_demo_runner()
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
    assert set(result.tables.keys()) == {"invoice", "contact", "customer"}


def test_demo_runner_accepts_explicit_overrides(tmp_path: Path) -> None:
    invoice_csv = tmp_path / "invoice.csv"
    contact_csv = tmp_path / "contact.csv"
    customer_csv = tmp_path / "customer.csv"
    for path, name in (
        (invoice_csv, "invoice"),
        (contact_csv, "contact"),
        (customer_csv, "customer"),
    ):
        _write_demo_csv(path, name)

    Phase4DemoRequest, Phase4DemoRunner = _load_phase4_demo_runner()
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


def test_demo_runner_records_failed_state(tmp_path: Path) -> None:
    overrides = _build_demo_overrides(tmp_path)
    contact_csv = overrides["contact"]
    contact_csv.write_text(
        "remote_id,name,email_address,is_customer,is_supplier,status,currency,company\n"
        "src_contact_1,Acme Contact,billing@acme.test,true,false,ACTIVE,USD,company_123\n",
        encoding="utf-8",
    )

    Phase4DemoRequest, Phase4DemoRunner = _load_phase4_demo_runner()
    runner = Phase4DemoRunner(output_root=tmp_path / "runs")
    result = runner.run(
        Phase4DemoRequest(
            run_id="run-failed",
            company_id="company_123",
            dataset="custom",
            sync_type="initial",
            input_paths=overrides,
        )
    )

    assert result.status == "failed"
    state = _read_run_state(result.run_state_path)
    assert state["status"] == "failed"
    assert "last_error" in state and state["last_error"]
    assert state["tables"]["invoice"]["status"] == "succeeded"
    assert state["tables"]["contact"]["status"] == "failed"
    assert "customer" not in state["tables"]


def test_demo_runner_rejects_duplicate_run(tmp_path: Path) -> None:
    seed_root = tmp_path / "seeds"
    seed_root.mkdir()
    for name in DEMO_CSV_FIXTURES:
        _write_demo_csv(seed_root / f"{name}.csv", name)

    Phase4DemoRequest, Phase4DemoRunner = _load_phase4_demo_runner()
    runner = Phase4DemoRunner(output_root=tmp_path / "runs")
    request = Phase4DemoRequest(
        run_id="run-duplicate",
        company_id="company_123",
        dataset="seeded",
        sync_type="initial",
        seed_root=seed_root,
    )

    runner.run(request)
    with pytest.raises(ValueError, match="already exists"):
        runner.run(request)


def test_demo_runner_rejects_override_validation(tmp_path: Path) -> None:
    Phase4DemoRequest, Phase4DemoRunner = _load_phase4_demo_runner()
    runner = Phase4DemoRunner(output_root=tmp_path / "runs")
    invoice_csv = tmp_path / "invoice.csv"
    contact_csv = tmp_path / "contact.csv"
    _write_demo_csv(invoice_csv, "invoice")
    _write_demo_csv(contact_csv, "contact")

    with pytest.raises(ValueError, match="missing override"):
        runner.run(
            Phase4DemoRequest(
                run_id="run-missing",
                company_id="company_123",
                dataset="custom",
                sync_type="initial",
                input_paths={"invoice": invoice_csv, "contact": contact_csv},
            )
        )

    customer_csv = tmp_path / "customer.csv"
    _write_demo_csv(customer_csv, "customer")
    extra_csv = tmp_path / "extra.csv"
    extra_csv.write_text("id\n1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported override"):
        runner.run(
            Phase4DemoRequest(
                run_id="run-extra",
                company_id="company_123",
                dataset="custom",
                sync_type="initial",
                input_paths={
                    "invoice": invoice_csv,
                    "contact": contact_csv,
                    "customer": customer_csv,
                    "extra": extra_csv,
                },
            )
        )


def test_demo_runner_rejects_invalid_run_id(tmp_path: Path) -> None:
    Phase4DemoRequest, Phase4DemoRunner = _load_phase4_demo_runner()
    runner = Phase4DemoRunner(output_root=tmp_path / "runs")
    overrides = _build_demo_overrides(tmp_path)

    for run_id in ("", "   ", "run/escape", "../bad", "bad\\run", ".."):
        with pytest.raises(ValueError):
            runner.run(
                Phase4DemoRequest(
                    run_id=run_id,
                    company_id="company_123",
                    dataset="custom",
                    sync_type="initial",
                    input_paths=overrides,
                )
            )
