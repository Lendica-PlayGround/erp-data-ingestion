# Phase 4 Demo Execution System Design

**Date:** April 19, 2026
**Scope:** Add a runnable Phase 4 demo execution system with one shared runner, a local dry-run-first CLI entrypoint, and JWT-gated dashboard APIs that trigger the same execution flow.

## Goal

Create a real execution system for the Phase 4 demo instead of a collection of isolated transformer and publisher utilities. The first version must let a developer run the Phase 4 flow locally end-to-end, inspect run state and generated artifacts, and trigger the same flow from the existing Mira dashboard while keeping the implementation ready for later Supabase S3 and ClickHouse publishing.

## Decisions

### 1. Use one shared execution core

The system will center on a single runner, `Phase4DemoRunner`, that owns the end-to-end lifecycle of a Phase 4 demo run.

That runner will:

- resolve the input dataset
- process `invoice`, `contact`, and `customer`
- choose the correct schema and serializer path for each table
- write local Parquet and manifest outputs
- persist run state for inspection and polling
- optionally publish through pluggable sinks later

Both the CLI and the dashboard APIs will call this same runner. The dashboard must not have its own parallel orchestration logic.

### 2. Make local dry-run the primary mode

The first version will default to dry-run mode.

Dry-run mode means:

- read the seeded or user-provided mid-layer CSVs
- transform them into canonical Phase 4 outputs
- write local Parquet and `manifest.json` files
- persist local run state and event summaries
- avoid any dependency on real Supabase S3 or ClickHouse availability

This is the primary developer workflow. Real publishing will remain a clean extension point on the same runner contract rather than a separate path.

### 3. Support fixed seeded inputs plus explicit per-table overrides

The first version must support:

- a fixed checked-in seeded demo dataset by default
- explicit CLI override paths for:
  - `invoice`
  - `contact`
  - `customer`

This preserves a deterministic demo path while still allowing local experimentation with custom mid-layer CSVs.

### 4. Keep JWT-only dashboard access

The dashboard integration must stay compatible with the existing JWT-gated access model.

The new Phase 4 APIs and page should:

- require the same JWT token model as the existing dashboard
- scope visibility by `(company_id, run_id)` claims
- avoid introducing a local auth bypass in v1

This keeps the demo execution system aligned with the intended production interaction model.

### 5. Add customer support in v1

The execution system must support:

- `invoice`
- `contact`
- `customer`

Current Phase 4 serializers only support `invoice.v1` and `contact.v1`. The new work must add a customer serializer path that maps `customer` rows into the canonical Contact-shaped target model used by the Phase 4 contract.

## Architecture

### Shared runner

Add a new execution layer in `src/erp_data_ingestion/phase4_demo.py` with a public runner class and typed request/result models.

Representative interface:

```python
runner = Phase4DemoRunner(...)
result = runner.run(request)
```

The runner responsibilities are:

1. validate the requested dataset shape
2. resolve actual per-table CSV paths
3. build a run workspace under a deterministic local output root
4. mark run state `running`
5. process `invoice`, `contact`, and `customer` in order
6. transform each table into local Parquet + manifest outputs
7. record per-table status, row counts, artifact paths, and events
8. mark the overall run `succeeded` or `failed`

The runner must preserve completed table outputs if a later table fails.

### CLI entrypoint

Add a local CLI entrypoint that invokes the shared runner directly.

Expected local usage:

```bash
export PYTHONPATH=$PWD/src:$PWD/mira
python -m erp_data_ingestion.phase4_demo run
```

Supported arguments:

- `--dataset seeded`
- `--input-invoice <path>`
- `--input-contact <path>`
- `--input-customer <path>`
- `--run-id <id>`
- `--company-id <id>`
- `--sync-type <initial|delta>`
- `--output-root <path>`
- future-compatible, but not primary in v1:
  - `--publish-mode dry-run|real`

CLI output should print:

- run id
- overall status
- per-table row counts
- artifact paths
- error summary on failure

### Dashboard integration

Extend the existing FastAPI dashboard app with Phase 4 demo endpoints that reuse the runner.

Add:

- `POST /api/phase4-demo/start`
- `GET /api/phase4-demo/status`
- `GET /api/phase4-demo/events`
- a Phase 4 dashboard HTML page or route that polls these endpoints

The start endpoint should:

1. validate the JWT
2. derive `(company_id, run_id)` from claims
3. reject duplicate concurrent runs for that scope
4. launch the runner in a background task
5. return the current run id and status

The status and events endpoints should read persisted local run state rather than in-memory globals so the page stays inspectable and the CLI and dashboard remain aligned.

## Data Model

### Inputs

The seeded dataset lives under `seeds/samples/midlayer-csv/`.

The runner resolves one CSV per supported table:

- `invoice`
- `contact`
- `customer`

For v1, the seeded layout may be simple and explicit rather than dynamically discovering many possible date partitions. Determinism matters more than flexibility here.

### Output layout

Dry-run outputs will live under:

```text
.mira_workspace/phase4-demo/runs/<run_id>/
```

Within that run root, table artifacts follow the existing partitioned lake structure:

```text
company_id=<company_id>/
  table=<table>/
    sync_type=<sync_type>/
      date=<YYYY-MM-DD>/
        run_id=<run_id>/
          <table>.parquet
          manifest.json
```

This keeps the dry-run layout consistent with the future published object key shape.

### Run state

Persist a run state file at:

```text
.mira_workspace/phase4-demo/runs/<run_id>/run_state.json
```

Minimum shape:

- `run_id`
- `company_id`
- `mode`
- `dataset`
- `status`
- `started_at`
- `finished_at`
- `tables`
- `events`
- `last_error`

Each `tables[table_name]` entry should include:

- `status`
- `input_path`
- `row_count`
- `schema_version`
- `parquet_path`
- `manifest_path`
- `error`

This file is the source of truth for the CLI summary and dashboard polling in v1.

## Error Handling

- Missing seeded fixture: fail before starting table processing.
- Missing override file: fail before starting table processing.
- Unsupported serializer mapping: fail clearly with the table and schema version in the error.
- One table failure: mark overall run failed, preserve completed table outputs.
- Concurrent dashboard start for same run: reject with a clear error response.
- Invalid `customer` row that cannot map to canonical contact shape: table fails and the overall run fails.

## Testing Strategy

### Automated tests

Add tests before implementation for:

- runner success in dry-run mode on seeded inputs
- explicit per-table override support
- customer serializer support
- run state persistence through terminal states
- dashboard start/status/events endpoints using the same runner contract
- duplicate concurrent run rejection

Existing transform and publisher tests remain in place and should continue passing.

### Manual smoke test

Local dry-run smoke test:

1. start the dashboard app
2. open the JWT-gated Phase 4 page
3. trigger the Phase 4 demo
4. verify local Parquet and manifest outputs exist
5. verify the page updates status until terminal
6. run the CLI against the seeded dataset
7. run the CLI again with one or more custom table overrides

## Rollout Plan

1. Add failing tests for the runner, customer serialization, and dashboard API shape.
2. Add customer serializer support.
3. Implement the shared runner and local run-state persistence.
4. Add the CLI entrypoint.
5. Add dashboard endpoints and a Phase 4 page integration.
6. Verify the local dry-run flow end-to-end.
7. Leave a clean adapter seam for later real Supabase S3 and ClickHouse publishing on the same runner.

## Acceptance Criteria

- A developer can run the Phase 4 demo locally from the CLI with no real infra dependencies.
- The local run writes Parquet and manifest files for `invoice`, `contact`, and `customer`.
- `customer` maps through a supported canonical serializer path.
- The dashboard can start and inspect the same run through JWT-gated APIs.
- CLI and dashboard use the same execution core.
- Run status is persisted to disk and survives long enough for inspection after completion.
- Custom per-table CSV path overrides work in v1.

## Out Of Scope

- replacing the real future Phase 3 trigger
- production job scheduling
- real Supabase S3 and ClickHouse publishing as the primary v1 mode
- local auth bypasses
- historical analytics, charts, or alerts
