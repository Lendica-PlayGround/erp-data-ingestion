from erp_data_ingestion.demo_dataset import load_fixed_phase4_demo


def test_load_fixed_phase4_demo_returns_expected_tables() -> None:
    dataset = load_fixed_phase4_demo()

    assert dataset.company_id == "acme-co"
    assert dataset.demo_name == "acme-co-fixed-demo"
    assert [table.table_name for table in dataset.tables] == [
        "invoice",
        "customer",
        "contact",
    ]
    assert dataset.tables[0].source_csv.name == "acme-co_invoices_initial_20260418.csv"
    assert dataset.tables[1].schema_version == "customer.v1"
    assert dataset.tables[2].sync_type == "initial"


def test_load_fixed_phase4_demo_exposes_manifests() -> None:
    dataset = load_fixed_phase4_demo()

    assert sorted(path.name for path in dataset.manifest_files) == [
        "2026-04-18.json",
        "2026-04-19.json",
    ]
    assert dataset.root.as_posix().endswith("seeds/samples/midlayer-csv/acme-co")
