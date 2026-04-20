# Phase 4 Demo Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a real seeded Phase 4 demo that reads fixed mid-layer CSV fixtures, publishes canonical Parquet artifacts to Supabase S3 storage, writes monitoring events to ClickHouse, and exposes a separate auto-refreshing Phase 4 page inside the existing Mira dashboard.

**Architecture:** Add a fixed-demo dataset loader and a Phase 4 orchestration runner under `src/erp_data_ingestion/`, align the serializers with the actual mid-layer CSV contract, and keep temporary control-plane state under `onboarding_runs.document.phase4`. Extend the existing Mira dashboard app with a dedicated Phase 4 route plus JSON start/state/events endpoints backed by the existing JWT access model, the Supabase onboarding store, and ClickHouse event reads.

**Tech Stack:** Python 3.12, pytest, FastAPI, Supabase Python client, boto3 S3-compatible uploads, clickhouse-connect, pyarrow/parquet

---

## File Structure

- `seeds/samples/midlayer-csv/acme-co/`
  - Real fixed demo fixtures for `invoices`, `customers`, `contacts`, sidecars, and manifests.
- `src/erp_data_ingestion/demo_dataset.py`
  - Fixed-demo fixture discovery and table metadata.
- `src/erp_data_ingestion/demo_runner.py`
  - Orchestrates fixture loading, transform, publish, and progress callbacks.
- `src/erp_data_ingestion/models.py`
  - Expands canonical contact shape so both `customers` and `contacts` can land in one target type.
- `src/erp_data_ingestion/serializers/invoice_v1.py`
  - Reads real Phase 1 invoice columns.
- `src/erp_data_ingestion/serializers/contact_v1.py`
  - Reads real Phase 1 contact columns.
- `src/erp_data_ingestion/serializers/customer_v1.py`
  - Maps mid-layer `customers` rows into canonical Contact output.
- `src/erp_data_ingestion/serializers/__init__.py`
  - Registry for `invoice.v1`, `customer.v1`, `contact.v1`.
- `src/erp_data_ingestion/adapters/clickhouse.py`
  - Existing write path plus read helpers for recent Phase 4 events.
- `mira/agent/models/onboarding.py`
  - Adds `phase4` state to the persisted onboarding document.
- `mira/agent/runtime/phase4_service.py`
  - Dashboard-facing orchestration, onboarding state patching, and event reads.
- `mira/agent/runtime/dashboard_app.py`
  - Existing dashboard plus a separate Phase 4 page and JSON APIs.
- `requirements.txt`
  - Ensure root environment includes dashboard and Supabase store dependencies.
- `README.md`
  - Document the demo flow and how to run the dashboard smoke test.
- `tests/test_demo_dataset.py`
  - Verifies seeded fixture discovery and manifest layout.
- `tests/test_serializers.py`
  - Verifies invoice/contact/customer serializer behavior against real mid-layer rows.
- `tests/test_phase4_transform.py`
  - Verifies transform path with real mid-layer-shaped rows.
- `tests/test_demo_runner.py`
  - Verifies orchestration, success state, and failure state behavior.
- `tests/test_adapters.py`
  - Verifies ClickHouse event query helper.
- `tests/test_dashboard_phase4.py`
  - Verifies JWT-scoped Phase 4 dashboard endpoints and auto-refresh data sources.

### Task 1: Add Fixed Demo Fixtures And Loader

**Files:**
- Create: `seeds/samples/midlayer-csv/acme-co/invoices/initial/acme-co_invoices_initial_20260418.csv`
- Create: `seeds/samples/midlayer-csv/acme-co/invoices/initial/acme-co_invoices_initial_20260418.csv.meta.json`
- Create: `seeds/samples/midlayer-csv/acme-co/invoices/delta/dt=2026-04-19/acme-co_invoices_delta_20260419_01HWXK9A2Z8F3Q4B7N5M6P1R2S.csv`
- Create: `seeds/samples/midlayer-csv/acme-co/invoices/delta/dt=2026-04-19/acme-co_invoices_delta_20260419_01HWXK9A2Z8F3Q4B7N5M6P1R2S.csv.meta.json`
- Create: `seeds/samples/midlayer-csv/acme-co/customers/initial/acme-co_customers_initial_20260418.csv`
- Create: `seeds/samples/midlayer-csv/acme-co/customers/initial/acme-co_customers_initial_20260418.csv.meta.json`
- Create: `seeds/samples/midlayer-csv/acme-co/contacts/initial/acme-co_contacts_initial_20260418.csv`
- Create: `seeds/samples/midlayer-csv/acme-co/contacts/initial/acme-co_contacts_initial_20260418.csv.meta.json`
- Create: `seeds/samples/midlayer-csv/acme-co/_manifest/2026-04-18.json`
- Create: `seeds/samples/midlayer-csv/acme-co/_manifest/2026-04-19.json`
- Create: `src/erp_data_ingestion/demo_dataset.py`
- Create: `tests/test_demo_dataset.py`
- Modify: `seeds/samples/midlayer-csv/README.md`

- [ ] **Step 1: Write the failing dataset-loader tests**

```python
from pathlib import Path

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
```

- [ ] **Step 2: Run the loader tests to verify they fail**

Run: `pytest -q tests/test_demo_dataset.py`

Expected: FAIL with `ModuleNotFoundError` or `ImportError` for `erp_data_ingestion.demo_dataset`.

- [ ] **Step 3: Implement the fixed dataset loader**

```python
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
    demo_root = (root or repo_root / "seeds" / "samples" / "midlayer-csv" / "acme-co").resolve()
    tables = [
        DemoTableInput(
            table_name="invoice",
            schema_version="invoice.v1",
            sync_type="initial",
            logical_date="2026-04-18",
            run_id="phase4-demo-20260418",
            source_csv=demo_root / "invoices" / "initial" / "acme-co_invoices_initial_20260418.csv",
            sidecar_json=demo_root / "invoices" / "initial" / "acme-co_invoices_initial_20260418.csv.meta.json",
        ),
        DemoTableInput(
            table_name="customer",
            schema_version="customer.v1",
            sync_type="initial",
            logical_date="2026-04-18",
            run_id="phase4-demo-20260418",
            source_csv=demo_root / "customers" / "initial" / "acme-co_customers_initial_20260418.csv",
            sidecar_json=demo_root / "customers" / "initial" / "acme-co_customers_initial_20260418.csv.meta.json",
        ),
        DemoTableInput(
            table_name="contact",
            schema_version="contact.v1",
            sync_type="initial",
            logical_date="2026-04-18",
            run_id="phase4-demo-20260418",
            source_csv=demo_root / "contacts" / "initial" / "acme-co_contacts_initial_20260418.csv",
            sidecar_json=demo_root / "contacts" / "initial" / "acme-co_contacts_initial_20260418.csv.meta.json",
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
```

- [ ] **Step 4: Add the exact demo fixture files**

```csv
# seeds/samples/midlayer-csv/acme-co/invoices/initial/acme-co_invoices_initial_20260418.csv
external_id,type,number,contact_external_id,issue_date,due_date,paid_on_date,memo,currency,exchange_rate,total_discount,sub_total,total_tax_amount,total_amount,balance,status,remote_was_deleted,_unmapped,_source_system,_source_record_id,_company_id,_ingested_at,_source_file,_mapping_version,_row_hash
inv_stripe_001,ACCOUNTS_RECEIVABLE,INV-001,cus_acme_001,2026-04-18T00:00:00Z,2026-04-30T00:00:00Z,,Annual subscription invoice,USD,1.0,0.0000,100.0000,5.0000,105.0000,25.0000,OPEN,false,{},stripe,in_001,acme-co,2026-04-18T08:00:00Z,seeds/samples/midlayer-csv/acme-co/invoices/initial/acme-co_invoices_initial_20260418.csv,stripe.invoice@0.1.0,hash-invoice-001
inv_stripe_002,ACCOUNTS_RECEIVABLE,INV-002,cus_acme_002,2026-04-18T00:00:00Z,2026-05-02T00:00:00Z,,Professional services invoice,USD,1.0,0.0000,250.0000,12.5000,262.5000,0.0000,PAID,false,{},stripe,in_002,acme-co,2026-04-18T08:00:00Z,seeds/samples/midlayer-csv/acme-co/invoices/initial/acme-co_invoices_initial_20260418.csv,stripe.invoice@0.1.0,hash-invoice-002
inv_stripe_003,ACCOUNTS_RECEIVABLE,INV-003,cus_acme_003,2026-04-18T00:00:00Z,2026-05-10T00:00:00Z,,Expansion invoice,USD,1.0,0.0000,400.0000,20.0000,420.0000,420.0000,OPEN,false,{},stripe,in_003,acme-co,2026-04-18T08:00:00Z,seeds/samples/midlayer-csv/acme-co/invoices/initial/acme-co_invoices_initial_20260418.csv,stripe.invoice@0.1.0,hash-invoice-003
```

```json
// seeds/samples/midlayer-csv/acme-co/invoices/initial/acme-co_invoices_initial_20260418.csv.meta.json
{
  "schema_version": "v1",
  "table": "invoices",
  "company_id": "acme-co",
  "source_system": "stripe",
  "sync_type": "initial",
  "run_id": "phase4-demo-20260418",
  "source_run_id": "airflow:stripe_invoices_initial__2026-04-18",
  "mapping_version": "stripe.invoice@0.1.0",
  "generated_at": "2026-04-18T08:00:15Z",
  "row_count": 3,
  "reject_count": 0,
  "sha256": "sha-invoices-initial"
}
```

```csv
# seeds/samples/midlayer-csv/acme-co/invoices/delta/dt=2026-04-19/acme-co_invoices_delta_20260419_01HWXK9A2Z8F3Q4B7N5M6P1R2S.csv
external_id,type,number,contact_external_id,issue_date,due_date,paid_on_date,memo,currency,exchange_rate,total_discount,sub_total,total_tax_amount,total_amount,balance,status,remote_was_deleted,_unmapped,_source_system,_source_record_id,_company_id,_ingested_at,_source_file,_mapping_version,_row_hash
inv_stripe_004,ACCOUNTS_RECEIVABLE,INV-004,cus_acme_001,2026-04-19T00:00:00Z,2026-05-15T00:00:00Z,,Delta renewal invoice,USD,1.0,0.0000,180.0000,9.0000,189.0000,189.0000,OPEN,false,{},stripe,in_004,acme-co,2026-04-19T08:00:00Z,seeds/samples/midlayer-csv/acme-co/invoices/delta/dt=2026-04-19/acme-co_invoices_delta_20260419_01HWXK9A2Z8F3Q4B7N5M6P1R2S.csv,stripe.invoice@0.1.0,hash-invoice-004
```

```json
// seeds/samples/midlayer-csv/acme-co/invoices/delta/dt=2026-04-19/acme-co_invoices_delta_20260419_01HWXK9A2Z8F3Q4B7N5M6P1R2S.csv.meta.json
{
  "schema_version": "v1",
  "table": "invoices",
  "company_id": "acme-co",
  "source_system": "stripe",
  "sync_type": "delta",
  "run_id": "01HWXK9A2Z8F3Q4B7N5M6P1R2S",
  "source_run_id": "airflow:stripe_invoices_delta__2026-04-19",
  "mapping_version": "stripe.invoice@0.1.0",
  "generated_at": "2026-04-19T08:00:15Z",
  "row_count": 1,
  "reject_count": 0,
  "sha256": "sha-invoices-delta"
}
```

```csv
# seeds/samples/midlayer-csv/acme-co/customers/initial/acme-co_customers_initial_20260418.csv
external_id,name,is_supplier,is_customer,email_address,tax_number,status,currency,remote_updated_at,phone_number,addresses,remote_was_deleted,_unmapped,_source_system,_source_record_id,_company_id,_ingested_at,_source_file,_mapping_version,_row_hash
cus_acme_001,Acme Holdings,false,true,finance@acme.example,TAX-ACME-001,ACTIVE,USD,2026-04-18T08:00:00Z,+1-415-555-0100,"[{""address_type"":""BILLING"",""city"":""San Francisco"",""country"":""US"",""full_address"":""100 Market St, San Francisco, CA"",""state"":""CA"",""street_1"":""100 Market St"",""zip_code"":""94105""}]",false,{},stripe,cus_001,acme-co,2026-04-18T08:00:00Z,seeds/samples/midlayer-csv/acme-co/customers/initial/acme-co_customers_initial_20260418.csv,stripe.customer@0.1.0,hash-customer-001
cus_acme_002,Beacon Retail,false,true,ap@beacon.example,TAX-BEACON-002,ACTIVE,USD,2026-04-18T08:00:00Z,+1-646-555-0130,"[{""address_type"":""BILLING"",""city"":""New York"",""country"":""US"",""full_address"":""20 Broadway, New York, NY"",""state"":""NY"",""street_1"":""20 Broadway"",""zip_code"":""10004""}]",false,{"description":"priority customer"},stripe,cus_002,acme-co,2026-04-18T08:00:00Z,seeds/samples/midlayer-csv/acme-co/customers/initial/acme-co_customers_initial_20260418.csv,stripe.customer@0.1.0,hash-customer-002
cus_acme_003,Cascade Partners,false,true,ops@cascade.example,TAX-CASCADE-003,ACTIVE,USD,2026-04-18T08:00:00Z,+1-206-555-0160,"[{""address_type"":""BILLING"",""city"":""Seattle"",""country"":""US"",""full_address"":""300 Pine St, Seattle, WA"",""state"":""WA"",""street_1"":""300 Pine St"",""zip_code"":""98101""}]",false,{},stripe,cus_003,acme-co,2026-04-18T08:00:00Z,seeds/samples/midlayer-csv/acme-co/customers/initial/acme-co_customers_initial_20260418.csv,stripe.customer@0.1.0,hash-customer-003
```

```json
// seeds/samples/midlayer-csv/acme-co/customers/initial/acme-co_customers_initial_20260418.csv.meta.json
{
  "schema_version": "v1",
  "table": "customers",
  "company_id": "acme-co",
  "source_system": "stripe",
  "sync_type": "initial",
  "run_id": "phase4-demo-20260418",
  "source_run_id": "airflow:stripe_customers_initial__2026-04-18",
  "mapping_version": "stripe.customer@0.1.0",
  "generated_at": "2026-04-18T08:00:15Z",
  "row_count": 3,
  "reject_count": 0,
  "sha256": "sha-customers-initial"
}
```

```csv
# seeds/samples/midlayer-csv/acme-co/contacts/initial/acme-co_contacts_initial_20260418.csv
external_id,first_name,last_name,account_external_id,addresses,email_addresses,phone_numbers,last_activity_at,remote_created_at,remote_was_deleted,_unmapped,_source_system,_source_record_id,_company_id,_ingested_at,_source_file,_mapping_version,_row_hash
contact_acme_001,Alice,Ng,cus_acme_001,"[{""address_type"":""PRIMARY"",""full_address"":""100 Market St, San Francisco, CA""}]","[{""email_address"":""alice.ng@acme.example"",""email_address_type"":""WORK""}]","[{""phone_number"":""+1-415-555-0101"",""phone_number_type"":""WORK""}]",2026-04-18T07:30:00Z,2026-04-10T09:00:00Z,false,{},google_sheets,row_001,acme-co,2026-04-18T08:00:00Z,seeds/samples/midlayer-csv/acme-co/contacts/initial/acme-co_contacts_initial_20260418.csv,gsheets.contact@0.1.0,hash-contact-001
contact_acme_002,Bruno,Diaz,cus_acme_002,"[{""address_type"":""PRIMARY"",""full_address"":""20 Broadway, New York, NY""}]","[{""email_address"":""bruno.diaz@beacon.example"",""email_address_type"":""WORK""}]","[{""phone_number"":""+1-646-555-0131"",""phone_number_type"":""WORK""}]",2026-04-18T07:45:00Z,2026-04-11T09:00:00Z,false,{},google_sheets,row_002,acme-co,2026-04-18T08:00:00Z,seeds/samples/midlayer-csv/acme-co/contacts/initial/acme-co_contacts_initial_20260418.csv,gsheets.contact@0.1.0,hash-contact-002
contact_acme_003,Chloe,Park,cus_acme_003,"[{""address_type"":""PRIMARY"",""full_address"":""300 Pine St, Seattle, WA""}]","[{""email_address"":""chloe.park@cascade.example"",""email_address_type"":""WORK""}]","[{""phone_number"":""+1-206-555-0161"",""phone_number_type"":""WORK""}]",2026-04-18T07:50:00Z,2026-04-12T09:00:00Z,false,{},google_sheets,row_003,acme-co,2026-04-18T08:00:00Z,seeds/samples/midlayer-csv/acme-co/contacts/initial/acme-co_contacts_initial_20260418.csv,gsheets.contact@0.1.0,hash-contact-003
```

```json
// seeds/samples/midlayer-csv/acme-co/contacts/initial/acme-co_contacts_initial_20260418.csv.meta.json
{
  "schema_version": "v1",
  "table": "contacts",
  "company_id": "acme-co",
  "source_system": "google_sheets",
  "sync_type": "initial",
  "run_id": "phase4-demo-20260418",
  "source_run_id": "airflow:gsheets_contacts_initial__2026-04-18",
  "mapping_version": "gsheets.contact@0.1.0",
  "generated_at": "2026-04-18T08:00:15Z",
  "row_count": 3,
  "reject_count": 0,
  "sha256": "sha-contacts-initial"
}
```

```json
// seeds/samples/midlayer-csv/acme-co/_manifest/2026-04-18.json
{
  "schema_version": "v1",
  "run_date": "2026-04-18",
  "run_id": "phase4-demo-20260418",
  "company_id": "acme-co",
  "generated_at": "2026-04-18T08:00:25Z",
  "runs": [
    {
      "table": "invoices",
      "sync_type": "initial",
      "file": "acme-co/invoices/initial/acme-co_invoices_initial_20260418.csv",
      "sha256": "sha-invoices-initial",
      "row_count": 3,
      "reject_count": 0,
      "source_system": "stripe",
      "mapping_version": "stripe.invoice@0.1.0"
    },
    {
      "table": "customers",
      "sync_type": "initial",
      "file": "acme-co/customers/initial/acme-co_customers_initial_20260418.csv",
      "sha256": "sha-customers-initial",
      "row_count": 3,
      "reject_count": 0,
      "source_system": "stripe",
      "mapping_version": "stripe.customer@0.1.0"
    },
    {
      "table": "contacts",
      "sync_type": "initial",
      "file": "acme-co/contacts/initial/acme-co_contacts_initial_20260418.csv",
      "sha256": "sha-contacts-initial",
      "row_count": 3,
      "reject_count": 0,
      "source_system": "google_sheets",
      "mapping_version": "gsheets.contact@0.1.0"
    }
  ],
  "validation": {
    "pydantic_validation_passed": true,
    "row_count_parity": true,
    "non_null_required_fields": true,
    "currency_amount_consistency": true,
    "primary_key_unique": true
  }
}
```

```json
// seeds/samples/midlayer-csv/acme-co/_manifest/2026-04-19.json
{
  "schema_version": "v1",
  "run_date": "2026-04-19",
  "run_id": "01HWXK9A2Z8F3Q4B7N5M6P1R2S",
  "company_id": "acme-co",
  "generated_at": "2026-04-19T08:00:25Z",
  "runs": [
    {
      "table": "invoices",
      "sync_type": "delta",
      "file": "acme-co/invoices/delta/dt=2026-04-19/acme-co_invoices_delta_20260419_01HWXK9A2Z8F3Q4B7N5M6P1R2S.csv",
      "sha256": "sha-invoices-delta",
      "row_count": 1,
      "reject_count": 0,
      "source_system": "stripe",
      "mapping_version": "stripe.invoice@0.1.0"
    }
  ],
  "validation": {
    "pydantic_validation_passed": true,
    "row_count_parity": true,
    "non_null_required_fields": true,
    "currency_amount_consistency": true,
    "primary_key_unique": true
  }
}
```

- [ ] **Step 5: Update the worked-example README**

```md
These files are now committed as runnable demo fixtures for the Phase 4 dashboard flow.
They intentionally mirror the documented Phase 1 contract closely enough for the Phase 4
demo runner to ingest them directly without a Phase 3 dependency.
```

- [ ] **Step 6: Run the dataset-loader tests to verify they pass**

Run: `pytest -q tests/test_demo_dataset.py`

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add \
  seeds/samples/midlayer-csv/README.md \
  seeds/samples/midlayer-csv/acme-co \
  src/erp_data_ingestion/demo_dataset.py \
  tests/test_demo_dataset.py
git commit -m "feat: add fixed phase4 demo fixtures"
```

### Task 2: Align Serializers With The Real Mid-Layer Contract

**Files:**
- Create: `src/erp_data_ingestion/serializers/customer_v1.py`
- Modify: `src/erp_data_ingestion/models.py`
- Modify: `src/erp_data_ingestion/serializers/__init__.py`
- Modify: `src/erp_data_ingestion/serializers/invoice_v1.py`
- Modify: `src/erp_data_ingestion/serializers/contact_v1.py`
- Modify: `tests/test_serializers.py`
- Modify: `tests/test_phase4_transform.py`
- Modify: `tests/test_models.py`

- [ ] **Step 1: Write failing serializer and transform tests against real mid-layer rows**

```python
from erp_data_ingestion.serializers import get_serializer


def test_customer_v1_serializer_maps_midlayer_customer_row_to_canonical_contact_payload() -> None:
    serializer = get_serializer(table="customer", schema_version="customer.v1")

    payload = serializer.serialize_row(
        {
            "external_id": "cus_acme_001",
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
        }
    )

    assert payload["id"] == "cus_acme_001"
    assert payload["name"] == "Acme Holdings"
    assert payload["is_customer"] is True
    assert payload["phone_numbers"][0]["phone_number"] == "+1-415-555-0100"


def test_contact_v1_serializer_maps_crm_contact_row_to_canonical_contact_payload() -> None:
    serializer = get_serializer(table="contact", schema_version="contact.v1")

    payload = serializer.serialize_row(
        {
            "external_id": "contact_acme_001",
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
```

```python
def test_transformer_writes_customer_rows_as_contact_parquet(tmp_path) -> None:
    input_csv = tmp_path / "acme-co_customers_initial_20260418.csv"
    input_csv.write_text(
        "\\n".join(
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
```

- [ ] **Step 2: Run the serializer and transform tests to verify they fail**

Run: `pytest -q tests/test_serializers.py tests/test_phase4_transform.py tests/test_models.py`

Expected: FAIL with unsupported `customer.v1`, key mismatches for `external_id`, and missing canonical contact fields.

- [ ] **Step 3: Expand the canonical contact model**

```python
@dataclass
class ContactRecord:
    id: str
    remote_id: Optional[str] = None
    name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email_address: Optional[str] = None
    email_addresses: List[Dict[str, Any]] = field(default_factory=list)
    tax_number: Optional[str] = None
    is_customer: Optional[bool] = None
    is_supplier: Optional[bool] = None
    status: Optional[str] = None
    currency: Optional[str] = None
    remote_updated_at: Optional[datetime] = None
    remote_created_at: Optional[datetime] = None
    remote_was_deleted: bool = False
    company: Optional[str] = None
    account_external_id: Optional[str] = None
    addresses: List[Dict[str, Any]] = field(default_factory=list)
    phone_numbers: List[Dict[str, Any]] = field(default_factory=list)
    remote_data: List[Dict[str, Any]] = field(default_factory=list)
    remote_fields: List[Dict[str, Any]] = field(default_factory=list)
    field_mappings: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.is_customer and not self.is_supplier:
            raise ValueError("contact must be marked as customer or supplier")
```

- [ ] **Step 4: Rewrite the serializer layer to accept real Phase 1 rows**

```python
# src/erp_data_ingestion/serializers/customer_v1.py
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from typing import Any

from erp_data_ingestion.models import ContactRecord


class CustomerV1Serializer:
    def serialize_row(self, row: dict[str, str]) -> dict[str, Any]:
        phone_numbers = []
        if row.get("phone_number"):
            phone_numbers.append({"phone_number": row["phone_number"], "phone_number_type": "WORK"})
        addresses = self._optional_json(row.get("addresses"), default=[])
        customer = ContactRecord(
            id=row["external_id"],
            remote_id=row.get("_source_record_id") or row["external_id"],
            name=self._optional_str(row.get("name")),
            email_address=self._optional_str(row.get("email_address")),
            email_addresses=[],
            tax_number=self._optional_str(row.get("tax_number")),
            is_customer=self._optional_bool(row.get("is_customer"), default=True),
            is_supplier=self._optional_bool(row.get("is_supplier"), default=False),
            status=self._optional_str(row.get("status")),
            currency=self._optional_str(row.get("currency")),
            remote_updated_at=self._optional_datetime(row.get("remote_updated_at")),
            remote_was_deleted=self._optional_bool(row.get("remote_was_deleted"), default=False),
            company=row.get("_company_id"),
            addresses=addresses,
            phone_numbers=phone_numbers,
        )
        return self._serialize_record(customer)

    def _serialize_record(self, record: Any) -> dict[str, Any]:
        payload = asdict(record)
        for key, value in list(payload.items()):
            if isinstance(value, datetime):
                payload[key] = value.isoformat().replace("+00:00", "Z")
            elif value == {} or value == []:
                payload[key] = None
        return payload

    def _optional_str(self, value: Any) -> str | None:
        if value in (None, ""):
            return None
        return str(value)

    def _optional_bool(self, value: Any, *, default: bool) -> bool:
        if value in (None, ""):
            return default
        lowered = str(value).strip().lower()
        return lowered in {"1", "true", "yes", "y"}

    def _optional_datetime(self, value: Any) -> datetime | None:
        if value in (None, ""):
            return None
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))

    def _optional_json(self, value: Any, *, default: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if value in (None, ""):
            return list(default)
        return json.loads(str(value))
```

```python
# src/erp_data_ingestion/serializers/invoice_v1.py
invoice = InvoiceRecord(
    id=row["external_id"],
    remote_id=row.get("_source_record_id") or row["external_id"],
    number=self._optional_str(row.get("number")),
    contact=self._optional_str(row.get("contact_external_id")),
    company=row.get("_company_id"),
    issue_date=self._optional_datetime(row.get("issue_date")),
    due_date=self._optional_datetime(row.get("due_date")),
    paid_on_date=self._optional_datetime(row.get("paid_on_date")),
    currency=self._optional_str(row.get("currency")),
    exchange_rate=self._optional_float(row.get("exchange_rate")),
    sub_total=self._optional_float(row.get("sub_total")),
    total_tax_amount=self._optional_float(row.get("total_tax_amount")),
    total_discount=self._optional_float(row.get("total_discount")),
    total_amount=self._optional_float(row.get("total_amount")),
    balance=self._optional_float(row.get("balance")),
    type=self._optional_str(row.get("type")),
    status=self._optional_str(row.get("status")),
    memo=self._optional_str(row.get("memo")),
    remote_was_deleted=self._optional_bool(row.get("remote_was_deleted")),
)
```

```python
# src/erp_data_ingestion/serializers/contact_v1.py
contact = ContactRecord(
    id=row["external_id"],
    remote_id=row.get("_source_record_id") or row["external_id"],
    name=" ".join(part for part in [row.get("first_name", ""), row.get("last_name", "")] if part).strip() or None,
    first_name=self._optional_str(row.get("first_name")),
    last_name=self._optional_str(row.get("last_name")),
    email_address=self._first_email(row.get("email_addresses")),
    email_addresses=self._optional_json(row.get("email_addresses"), default=[]),
    is_customer=True,
    is_supplier=False,
    account_external_id=self._optional_str(row.get("account_external_id")),
    company=self._optional_str(row.get("account_external_id")),
    addresses=self._optional_json(row.get("addresses"), default=[]),
    phone_numbers=self._optional_json(row.get("phone_numbers"), default=[]),
    remote_created_at=self._optional_datetime(row.get("remote_created_at")),
    remote_was_deleted=self._optional_bool(row.get("remote_was_deleted")),
)
```

```python
# src/erp_data_ingestion/serializers/__init__.py
from erp_data_ingestion.serializers.customer_v1 import CustomerV1Serializer

if table == "customer" and schema_version == "customer.v1":
    return CustomerV1Serializer()
```

- [ ] **Step 5: Run the serializer and transform tests to verify they pass**

Run: `pytest -q tests/test_serializers.py tests/test_phase4_transform.py tests/test_models.py`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add \
  src/erp_data_ingestion/models.py \
  src/erp_data_ingestion/serializers/__init__.py \
  src/erp_data_ingestion/serializers/invoice_v1.py \
  src/erp_data_ingestion/serializers/contact_v1.py \
  src/erp_data_ingestion/serializers/customer_v1.py \
  tests/test_serializers.py \
  tests/test_phase4_transform.py \
  tests/test_models.py
git commit -m "feat: align phase4 serializers with midlayer contract"
```

### Task 3: Add The Phase 4 Demo Runner And Persisted Phase 4 State

**Files:**
- Create: `src/erp_data_ingestion/demo_runner.py`
- Create: `tests/test_demo_runner.py`
- Modify: `mira/agent/models/onboarding.py`

- [ ] **Step 1: Write the failing runner tests**

```python
from pathlib import Path
from uuid import uuid4

from agent.models.onboarding import OnboardingState, SourceProfile
from erp_data_ingestion.demo_dataset import load_fixed_phase4_demo
from erp_data_ingestion.demo_runner import Phase4DemoRunner


class FakePublisher:
    def __init__(self) -> None:
        self.calls = []

    def publish(self, lake_result):
        self.calls.append(lake_result.table)
        return type(
            "PublishedRun",
            (),
            {
                "parquet_uri": f"s3://phase4-lake/{lake_result.table}.parquet",
                "manifest_uri": f"s3://phase4-lake/{lake_result.table}.manifest.json",
                "run_metadata": lake_result.run_metadata,
            },
        )()


def test_demo_runner_reports_success_for_all_tables(tmp_path: Path) -> None:
    events = []
    dataset = load_fixed_phase4_demo()
    runner = Phase4DemoRunner(
        output_root=tmp_path / "lake",
        publisher=FakePublisher(),
        on_progress=events.append,
    )

    result = runner.run(dataset=dataset, run_id="run-123")

    assert result.status == "succeeded"
    assert [table["table"] for table in result.tables] == ["invoice", "customer", "contact"]
    assert events[0]["status"] == "running"
    assert events[-1]["status"] == "succeeded"


def test_demo_runner_reports_failure_and_stops_on_first_error(tmp_path: Path) -> None:
    events = []
    dataset = load_fixed_phase4_demo()
    broken_dataset = dataset.__class__(
        demo_name=dataset.demo_name,
        company_id=dataset.company_id,
        root=dataset.root,
        tables=[
            dataset.tables[0].__class__(**{**dataset.tables[0].__dict__, "source_csv": dataset.root / "missing.csv"}),
            *dataset.tables[1:],
        ],
        manifest_files=dataset.manifest_files,
    )
    runner = Phase4DemoRunner(output_root=tmp_path / "lake", publisher=FakePublisher(), on_progress=events.append)

    result = runner.run(dataset=broken_dataset, run_id="run-999")

    assert result.status == "failed"
    assert "missing.csv" in result.last_error
    assert events[-1]["status"] == "failed"
```

- [ ] **Step 2: Run the runner tests to verify they fail**

Run: `pytest -q tests/test_demo_runner.py`

Expected: FAIL with `ModuleNotFoundError` for `erp_data_ingestion.demo_runner`.

- [ ] **Step 3: Add typed Phase 4 state to the onboarding document**

```python
class OnboardingState(BaseModel):
    run_id: UUID
    company_id: str
    state: OnboardingPhaseState = "intake"
    source: SourceProfile = Field(default_factory=SourceProfile)
    tables_in_scope: list[str] = Field(default_factory=list)
    artifacts_collected: list[ArtifactCollected] = Field(default_factory=list)
    table_descriptions: list[TableDescription] = Field(default_factory=list)
    column_descriptions: list[ColumnDescription] = Field(default_factory=list)
    mapping_contract: Optional[dict[str, Any]] = None
    approval: Approval = Field(default_factory=Approval)
    blockers: list[Blocker] = Field(default_factory=list)
    next_question: Optional[str] = None
    confidence_overall: float = 0.0
    phase3: dict[str, Any] = Field(default_factory=dict)
    phase4: dict[str, Any] = Field(default_factory=dict)
```

- [ ] **Step 4: Implement the demo runner with progress callbacks**

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

from erp_data_ingestion.demo_dataset import FixedPhase4DemoDataset
from erp_data_ingestion.phase4 import Phase4Transformer


@dataclass
class Phase4DemoRunResult:
    status: str
    tables: list[dict[str, Any]]
    last_error: str | None = None


class Phase4DemoRunner:
    def __init__(
        self,
        *,
        output_root: Path,
        publisher: Any,
        on_progress: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.output_root = output_root
        self.publisher = publisher
        self.on_progress = on_progress or (lambda _: None)

    def run(self, *, dataset: FixedPhase4DemoDataset, run_id: str) -> Phase4DemoRunResult:
        started_at = datetime.now(timezone.utc).isoformat()
        table_summaries: list[dict[str, Any]] = []
        self.on_progress({"status": "running", "started_at": started_at, "run_id": run_id, "tables": []})
        try:
            for table in dataset.tables:
                transformer = Phase4Transformer(schema_version=table.schema_version)
                logical_date = date.fromisoformat(table.logical_date)
                lake_result = transformer.transform_midlayer_csv(
                    input_csv=table.source_csv,
                    output_root=self.output_root,
                    table=table.table_name,
                    company_id=dataset.company_id,
                    sync_type=table.sync_type,
                    run_id=run_id,
                    logical_date=logical_date,
                )
                published = self.publisher.publish(lake_result)
                summary = {
                    "table": table.table_name,
                    "status": "succeeded",
                    "source_csv": str(table.source_csv),
                    "row_count": lake_result.row_count,
                    "output_parquet_uri": published.parquet_uri,
                    "manifest_uri": published.manifest_uri,
                    "error": None,
                }
                table_summaries.append(summary)
                self.on_progress({"status": "running", "run_id": run_id, "tables": table_summaries})
        except Exception as exc:
            message = str(exc)
            self.on_progress({"status": "failed", "run_id": run_id, "tables": table_summaries, "last_error": message})
            return Phase4DemoRunResult(status="failed", tables=table_summaries, last_error=message)
        self.on_progress({"status": "succeeded", "run_id": run_id, "tables": table_summaries, "last_error": None})
        return Phase4DemoRunResult(status="succeeded", tables=table_summaries)
```

- [ ] **Step 5: Run the runner tests to verify they pass**

Run: `pytest -q tests/test_demo_runner.py`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add \
  mira/agent/models/onboarding.py \
  src/erp_data_ingestion/demo_runner.py \
  tests/test_demo_runner.py
git commit -m "feat: add phase4 demo runner"
```

### Task 4: Add ClickHouse Event Reads And Dashboard Service

**Files:**
- Create: `mira/agent/runtime/phase4_service.py`
- Modify: `src/erp_data_ingestion/adapters/clickhouse.py`
- Modify: `tests/test_adapters.py`

- [ ] **Step 1: Write failing adapter and service tests**

```python
from datetime import datetime, timezone

from erp_data_ingestion.adapters.clickhouse import ClickHouseTelemetrySink


class FakeQueryClient:
    def __init__(self) -> None:
        self.queries = []

    def query(self, sql: str, parameters: dict[str, object]):
        self.queries.append((sql, parameters))
        return type(
            "Result",
            (),
            {
                "result_rows": [
                    ["phase4.transform.completed", "2026-04-18T08:00:00+00:00", '{"run_id":"run-1","table":"invoice"}']
                ]
            },
        )()


def test_clickhouse_sink_lists_recent_events_for_run() -> None:
    sink = ClickHouseTelemetrySink(client=FakeQueryClient())

    rows = sink.list_events(run_id="run-1", limit=10)

    assert rows[0]["event_name"] == "phase4.transform.completed"
    assert rows[0]["attributes"]["table"] == "invoice"
```

```python
def test_phase4_service_initializes_running_state(monkeypatch) -> None:
    state = OnboardingState(run_id=uuid4(), company_id="acme-co", source=SourceProfile(system="stripe"))
    store = InMemoryStateStore()
    store.put(state)
    service = Phase4DashboardService(store=store, clickhouse=FakeClickHouseAdapter(), runner_factory=fake_runner_factory)

    updated = service.start_demo(run_id=state.run_id, company_id="acme-co")

    assert updated["status"] == "running"
    assert updated["demo_dataset"] == "acme-co-fixed-demo"
```

- [ ] **Step 2: Run the adapter and service tests to verify they fail**

Run: `pytest -q tests/test_adapters.py tests/test_dashboard_phase4.py -k "clickhouse_sink_lists_recent_events_for_run or phase4_service_initializes_running_state"`

Expected: FAIL because `list_events` and `Phase4DashboardService` do not exist.

- [ ] **Step 3: Extend the ClickHouse adapter with a read helper**

```python
def list_events(self, *, run_id: str, limit: int = 25) -> list[dict[str, Any]]:
    result = self.client.query(
        """
        SELECT event_name, occurred_at, attributes_json
        FROM phase4_telemetry_events
        WHERE JSONExtractString(attributes_json, 'run_id') = %(run_id)s
        ORDER BY occurred_at DESC
        LIMIT %(limit)s
        """,
        parameters={"run_id": run_id, "limit": limit},
    )
    rows = []
    for event_name, occurred_at, attributes_json in result.result_rows:
        rows.append(
            {
                "event_name": event_name,
                "occurred_at": str(occurred_at),
                "attributes": json.loads(attributes_json),
            }
        )
    return rows
```

- [ ] **Step 4: Implement the dashboard-facing service**

```python
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import UUID

from agent.stores.base import StateStore
from agent.stores.supabase_store import store_from_env
from erp_data_ingestion.adapters.clickhouse import ClickHouseTelemetrySink
from erp_data_ingestion.demo_dataset import load_fixed_phase4_demo
from erp_data_ingestion.demo_runner import Phase4DemoRunner
from erp_data_ingestion.publish import Phase4Publisher


class Phase4DashboardService:
    def __init__(
        self,
        *,
        store: StateStore,
        clickhouse: ClickHouseTelemetrySink,
        runner_factory: Callable[[Path, Any, Callable[[dict[str, Any]], None]], Phase4DemoRunner] | None = None,
    ) -> None:
        self.store = store
        self.clickhouse = clickhouse
        self.runner_factory = runner_factory or self._default_runner

    def get_state(self, *, run_id: UUID) -> dict[str, Any]:
        state = self.store.get(run_id)
        if state is None:
            raise KeyError(f"Unknown run_id {run_id}")
        return state.phase4 or {"status": "idle", "tables": []}

    def start_demo(self, *, run_id: UUID, company_id: str) -> dict[str, Any]:
        current = self.get_state(run_id=run_id)
        if current.get("status") == "running":
            raise ValueError("Phase 4 demo already running")
        phase4 = {
            "status": "running",
            "demo_dataset": "acme-co-fixed-demo",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "finished_at": None,
            "last_error": None,
            "tables": [],
        }
        self.store.patch(run_id, {"phase4": phase4}, "phase4_demo_start")
        return phase4

    def record_progress(self, *, run_id: UUID, update: dict[str, Any]) -> None:
        current = self.get_state(run_id=run_id)
        merged = {**current, **update}
        if merged["status"] in {"succeeded", "failed"} and not merged.get("finished_at"):
            merged["finished_at"] = datetime.now(timezone.utc).isoformat()
        self.store.patch(run_id, {"phase4": merged}, "phase4_demo_progress")

    def list_events(self, *, run_id: UUID, limit: int = 25) -> list[dict[str, Any]]:
        return self.clickhouse.list_events(run_id=str(run_id), limit=limit)

    def run_demo(self, *, run_id: UUID) -> None:
        dataset = load_fixed_phase4_demo()
        runner = self.runner_factory(
            output_root=Path(".mira_workspace") / "phase4-demo",
            publisher=Phase4Publisher.from_env(),
            on_progress=lambda update: self.record_progress(run_id=run_id, update=update),
        )
        runner.run(dataset=dataset, run_id=str(run_id))

    def _default_runner(self, **kwargs: Any) -> Phase4DemoRunner:
        return Phase4DemoRunner(**kwargs)


def service_from_env() -> Phase4DashboardService:
    return Phase4DashboardService(
        store=store_from_env(),
        clickhouse=ClickHouseTelemetrySink.from_env(),
    )
```

- [ ] **Step 5: Run the adapter and service tests to verify they pass**

Run: `pytest -q tests/test_adapters.py tests/test_dashboard_phase4.py -k "clickhouse_sink_lists_recent_events_for_run or phase4_service_initializes_running_state"`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add \
  src/erp_data_ingestion/adapters/clickhouse.py \
  mira/agent/runtime/phase4_service.py \
  tests/test_adapters.py \
  tests/test_dashboard_phase4.py
git commit -m "feat: add phase4 dashboard service"
```

### Task 5: Build The Separate Phase 4 Dashboard Page And Endpoints

**Files:**
- Modify: `mira/agent/runtime/dashboard_app.py`
- Modify: `requirements.txt`
- Modify: `README.md`
- Modify: `tests/test_dashboard_phase4.py`

- [ ] **Step 1: Write the failing dashboard endpoint tests**

```python
from uuid import uuid4

import jwt
from fastapi.testclient import TestClient

from mira.agent.runtime.dashboard_app import _build_app


def test_phase4_dashboard_page_renders_separate_panel(monkeypatch) -> None:
    token = jwt.encode({"company_id": "acme-co", "run_id": str(uuid4())}, "test-secret", algorithm="HS256")
    monkeypatch.setenv("MIRA_JWT_SECRET", "test-secret")
    client = TestClient(_build_app())

    response = client.get(f"/dashboard/phase4?token={token}")

    assert response.status_code == 200
    assert "Phase 4 Demo" in response.text
    assert "Start Phase 4 Demo" in response.text
    assert "Onboarding run" not in response.text


def test_phase4_dashboard_state_endpoint_returns_phase4_summary(monkeypatch) -> None:
    run_id = str(uuid4())
    token = jwt.encode({"company_id": "acme-co", "run_id": run_id}, "test-secret", algorithm="HS256")
    monkeypatch.setenv("MIRA_JWT_SECRET", "test-secret")
    client = TestClient(_build_app())

    response = client.get(f"/api/phase4/state?token={token}")
    assert response.status_code == 200
    assert response.json()["status"] in {"idle", "running", "succeeded", "failed"}
```

- [ ] **Step 2: Run the dashboard tests to verify they fail**

Run: `pytest -q tests/test_dashboard_phase4.py`

Expected: FAIL because the Phase 4 page and API endpoints do not exist.

- [ ] **Step 3: Add the missing runtime dependencies**

```text
# requirements.txt
fastapi>=0.115,<1
uvicorn>=0.30,<1
supabase>=2.10,<3
```

- [ ] **Step 4: Implement the separate Phase 4 page and JSON endpoints**

```python
from typing import Annotated

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse

from agent.runtime.phase4_service import service_from_env


@app.get("/dashboard/phase4", response_class=HTMLResponse)
def phase4_dashboard(token: Annotated[str, Query(description="HS256 JWT")]):
    claims = _decode_claims(token, secret)
    company = claims.get("company_id", "")
    run_id = claims.get("run_id", "")
    body = f"""<!doctype html>
<html>
  <head>
    <meta charset="utf-8">
    <title>Phase 4 Demo — {company}</title>
  </head>
  <body>
    <h1>Phase 4 Demo</h1>
    <p><strong>company_id</strong>: {company}</p>
    <p><strong>run_id</strong>: {run_id}</p>
    <button id="start-btn">Start Phase 4 Demo</button>
    <pre id="summary"></pre>
    <pre id="events"></pre>
    <script>
      const token = new URLSearchParams(window.location.search).get("token");
      let pollHandle = null;

      async function loadState() {{
        const state = await fetch(`/api/phase4/state?token=${{token}}`).then((r) => r.json());
        const events = await fetch(`/api/phase4/events?token=${{token}}`).then((r) => r.json());
        document.getElementById("summary").textContent = JSON.stringify(state, null, 2);
        document.getElementById("events").textContent = JSON.stringify(events, null, 2);
        if (state.status === "running") {{
          if (!pollHandle) {{
            pollHandle = setInterval(loadState, 3000);
          }}
        }} else if (pollHandle) {{
          clearInterval(pollHandle);
          pollHandle = null;
        }}
      }}

      document.getElementById("start-btn").addEventListener("click", async () => {{
        await fetch(`/api/phase4/start?token=${{token}}`, {{ method: "POST" }});
        loadState();
      }});

      loadState();
    </script>
  </body>
</html>"""
    return HTMLResponse(body)


@app.get("/api/phase4/state")
def phase4_state(token: Annotated[str, Query(description="HS256 JWT")]):
    claims = _decode_claims(token, secret)
    service = service_from_env()
    return JSONResponse(service.get_state(run_id=UUID(claims["run_id"])))


@app.get("/api/phase4/events")
def phase4_events(token: Annotated[str, Query(description="HS256 JWT")]):
    claims = _decode_claims(token, secret)
    service = service_from_env()
    return JSONResponse(service.list_events(run_id=UUID(claims["run_id"])))


@app.post("/api/phase4/start")
def phase4_start(background_tasks: BackgroundTasks, token: Annotated[str, Query(description="HS256 JWT")]):
    claims = _decode_claims(token, secret)
    service = service_from_env()
    phase4 = service.start_demo(run_id=UUID(claims["run_id"]), company_id=claims["company_id"])
    background_tasks.add_task(service.run_demo, run_id=UUID(claims["run_id"]))
    return JSONResponse(phase4)
```

- [ ] **Step 5: Document the demo run path**

```md
### 7. Run the Phase 4 demo dashboard

1. Ensure `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_STORAGE_S3_*`,
   `CLICKHOUSE_*`, and `MIRA_JWT_SECRET` are set in `.env`.
2. Start the dashboard:

   ```bash
   PYTHONPATH=$PWD/src:$PWD/mira python -m agent.runtime.cli dashboard
   ```

3. Open the JWT-scoped Phase 4 page:

   ```text
   http://127.0.0.1:8090/dashboard/phase4?token=<jwt>
   ```

4. Click `Start Phase 4 Demo` and verify Supabase artifact uploads and ClickHouse events.
```

- [ ] **Step 6: Run the dashboard and full verification suite**

Run: `pytest -q tests/test_demo_dataset.py tests/test_serializers.py tests/test_phase4_transform.py tests/test_demo_runner.py tests/test_adapters.py tests/test_dashboard_phase4.py tests/test_publish.py tests/test_models.py`

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add \
  mira/agent/runtime/dashboard_app.py \
  requirements.txt \
  README.md \
  tests/test_dashboard_phase4.py
git commit -m "feat: add phase4 demo dashboard page"
```

## Self-Review Checklist

- [ ] The fixture task creates actual seed files, not just a README update.
- [ ] Serializer tasks use the real Phase 1 field names (`external_id`, `contact_external_id`, `email_addresses`, metadata columns) instead of the old simplified test shape.
- [ ] The runner task covers success and failure state updates.
- [ ] The dashboard task adds a separate Phase 4 page and leaves `/dashboard` intact.
- [ ] The final test command covers every new unit and integration-style test file in this plan.
