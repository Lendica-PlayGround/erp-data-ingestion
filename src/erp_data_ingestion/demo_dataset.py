from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DemoTableInput:
    table_name: str
    schema_version: str
    sync_type: str
    logical_date: str
    run_id: str
    source_csv: Path
    sidecar_json: Path


@dataclass(frozen=True)
class FixedPhase4DemoDataset:
    demo_name: str
    company_id: str
    root: Path
    tables: list[DemoTableInput]
    manifest_files: list[Path]


def load_fixed_phase4_demo(root: Path | None = None) -> FixedPhase4DemoDataset:
    repo_root = Path(__file__).resolve().parents[2]
    demo_root = (
        root or repo_root / "seeds" / "samples" / "midlayer-csv" / "acme-co"
    ).resolve()

    tables = [
        DemoTableInput(
            table_name="invoice",
            schema_version="invoice.v1",
            sync_type="initial",
            logical_date="2026-04-18",
            run_id="phase4-demo-20260418",
            source_csv=demo_root
            / "invoices"
            / "initial"
            / "acme-co_invoices_initial_20260418.csv",
            sidecar_json=demo_root
            / "invoices"
            / "initial"
            / "acme-co_invoices_initial_20260418.csv.meta.json",
        ),
        DemoTableInput(
            table_name="customer",
            schema_version="customer.v1",
            sync_type="initial",
            logical_date="2026-04-18",
            run_id="phase4-demo-20260418",
            source_csv=demo_root
            / "customers"
            / "initial"
            / "acme-co_customers_initial_20260418.csv",
            sidecar_json=demo_root
            / "customers"
            / "initial"
            / "acme-co_customers_initial_20260418.csv.meta.json",
        ),
        DemoTableInput(
            table_name="contact",
            schema_version="contact.v1",
            sync_type="initial",
            logical_date="2026-04-18",
            run_id="phase4-demo-20260418",
            source_csv=demo_root
            / "contacts"
            / "initial"
            / "acme-co_contacts_initial_20260418.csv",
            sidecar_json=demo_root
            / "contacts"
            / "initial"
            / "acme-co_contacts_initial_20260418.csv.meta.json",
        ),
    ]
    for table in tables:
        if not table.source_csv.exists():
            raise FileNotFoundError(f"Missing demo csv: {table.source_csv}")
        if not table.sidecar_json.exists():
            raise FileNotFoundError(f"Missing demo sidecar: {table.sidecar_json}")

    manifest_files = [
        demo_root / "_manifest" / "2026-04-18.json",
        demo_root / "_manifest" / "2026-04-19.json",
    ]
    for path in manifest_files:
        if not path.exists():
            raise FileNotFoundError(f"Missing demo manifest: {path}")

    return FixedPhase4DemoDataset(
        demo_name="acme-co-fixed-demo",
        company_id="acme-co",
        root=demo_root,
        tables=tables,
        manifest_files=manifest_files,
    )
