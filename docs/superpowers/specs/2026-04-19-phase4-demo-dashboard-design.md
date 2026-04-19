# Phase 4 Demo Dashboard Design

**Date:** April 19, 2026
**Scope:** Add a real seeded Phase 4 demo that ingests fixed mid-layer fixtures into the real Supabase lake bucket, emits ClickHouse telemetry, and exposes a dedicated auto-refreshing Phase 4 page inside the existing Mira dashboard app.

## Goal

Create a usable end-to-end demo for the Phase 4 handoff from mid-layer CSVs to target lake storage and monitoring without waiting for the Phase 3 validation loop. The demo should use one fixed seeded tenant, run against real Supabase S3-compatible storage and real ClickHouse, and surface run status, artifact links, and recent events from a separate Phase 4 dashboard page.

## Decisions

### 1. Reuse the existing dashboard app and auth model

The existing JWT-scoped Mira dashboard app remains the host application. Phase 4 gets a separate page or panel under the same app rather than a second service or a crowded extension of the current onboarding page.

- Keep the existing `/dashboard` onboarding view intact.
- Add a separate Phase 4 route, for example `/dashboard/phase4`, under the same JWT access model.
- Continue scoping access by `(company_id, run_id)` from the JWT claims.

This keeps authentication, run ownership, and deployment simple while preserving UI separation.

### 2. Reuse `onboarding_runs` as the temporary control plane

For this first version, Phase 4 state lives under `onboarding_runs.document.phase4` rather than a new Phase 4 run table.

The dashboard-triggered demo is temporary infrastructure until the real Phase 3 validation loop becomes the trigger. Reusing `onboarding_runs` avoids duplicating the control plane too early while still leaving room to extract Phase 4 state later if needed.

### 3. Support all three seeded tables

The demo must process:

- `invoice`
- `customer`
- `contact`

The canonical Phase 4 target model remains:

- `invoice` -> canonical Invoice object
- `contact` -> canonical Contact object
- `customer` -> canonical Contact object

This means the Phase 4 package needs a dedicated customer-to-canonical-contact serializer or equivalent transform path in addition to the existing invoice and contact paths.

### 4. Use one fixed seeded demo dataset

The first version does not allow dataset selection from the UI.

- The dashboard exposes a single `Start Phase 4 Demo` action.
- That action runs one fixed tenant fixture from `seeds/samples/midlayer-csv/`.
- There is only one active Phase 4 run at a time per onboarding run.

This keeps the behavior deterministic and reduces the amount of dashboard input handling required before the real Phase 3 trigger exists.

### 5. Keep the first monitoring view intentionally narrow

The Phase 4 dashboard page should show:

- overall run status
- started / finished timestamps
- per-table status and row counts
- artifact links
- recent events and errors from ClickHouse

It should auto-refresh while a run is active, then stop polling once the run reaches a terminal state.

The first version should not include charts, trend panels, or alerting logic. The goal is to prove the write path and monitoring integration, not to over-design observability before the telemetry schema stabilizes.

## Architecture

### Dashboard backend

The existing Mira dashboard FastAPI app gains:

- a new HTML page for Phase 4
- a JSON endpoint to fetch Phase 4 run state
- a JSON endpoint to start the fixed demo run
- a JSON endpoint to fetch recent ClickHouse-backed events for the current run

The start action must:

1. validate the JWT
2. load the `onboarding_runs` row for the current run
3. refuse duplicate concurrent runs if `document.phase4.status == "running"`
4. write the initial Phase 4 state into `document.phase4`
5. launch the Phase 4 runner for the fixed demo dataset

### Phase 4 runner

Add a dedicated orchestration layer in the Phase 4 package that sits above the existing transformer and publisher.

Responsibilities:

- locate the fixed seeded mid-layer input files
- iterate the three demo tables
- choose the correct schema version per table
- transform each table into partitioned Parquet
- upload Parquet and manifest artifacts to the real Supabase lake bucket
- write run metadata and telemetry events into ClickHouse
- patch `onboarding_runs.document.phase4` as progress advances
- capture and persist failure details if any table fails

This runner is the temporary ingestion initiation system until the Phase 3 validation loop owns the trigger.

### Seeded mid-layer fixtures

The repo already documents a concrete worked example in `seeds/samples/midlayer-csv/README.md`, but the actual CSV fixtures are missing. This design requires populating that directory with a real fixed tenant dataset matching the documented Phase 1 contract.

Required fixture set:

- one fixed tenant, e.g. `acme-co`
- initial CSV + sidecar files for `invoices`, `customers`, `contacts`
- at least one delta invoice example
- `_manifest` files for the documented dates

The files must be realistic enough to exercise:

- invoice transforms
- contact transforms
- customer-to-contact transforms
- major-unit money normalization already assumed by the mid-layer contract
- realistic metadata sidecars and manifest structure

### ClickHouse-backed monitoring

ClickHouse remains the system of record for recent telemetry rows shown on the Phase 4 page. The dashboard reads current summary state from `onboarding_runs.document.phase4` and reads recent event rows from ClickHouse.

For v1, ClickHouse data should be sufficient to support:

- recent event name
- event timestamp
- event attributes JSON
- surfaced error rows for failed tables or failed runs

## Data Flow

1. User opens the existing JWT-gated dashboard and navigates to the new Phase 4 page.
2. The page loads current `document.phase4` state and any recent ClickHouse events for the current `(company_id, run_id)`.
3. User clicks `Start Phase 4 Demo`.
4. The backend verifies the JWT and checks whether a Phase 4 run is already active.
5. The backend records:
   - `status = "running"`
   - `started_at`
   - fixed demo dataset identity
   - empty table summaries
6. The backend launches the Phase 4 runner.
7. The runner reads the fixed seeded CSV inputs from `seeds/samples/midlayer-csv/`.
8. The runner processes `invoice`, `customer`, and `contact` in order.
9. For each table:
   - transform rows into canonical objects
   - write local Parquet + manifest
   - upload artifacts to the real Supabase bucket
   - write ClickHouse telemetry
   - patch table-level progress into `document.phase4`
10. On success, the backend marks the overall Phase 4 state `succeeded` with `finished_at`.
11. On failure, the backend marks the overall Phase 4 state `failed`, stores the top-level error, and preserves any successful table outputs already completed.
12. The Phase 4 page auto-refreshes every few seconds while the run is active and stops once the run is terminal.

## State Shape

`onboarding_runs.document.phase4` should be added as a small explicit structure. The exact serialized shape can be implemented as a Pydantic model or a disciplined dict, but it must contain at least:

- `status`: `idle | running | succeeded | failed`
- `demo_dataset`
- `started_at`
- `finished_at`
- `last_error`
- `tables`

Each table entry under `tables` should contain:

- `status`
- `source_csv`
- `row_count`
- `output_parquet_uri`
- `manifest_uri`
- `error`

This state is intentionally summary-level. Detailed recent events stay in ClickHouse.

## Error Handling

- If the seeded fixture set is incomplete or missing, the run must fail fast with a clear error recorded in `document.phase4.last_error`.
- If one table fails, the overall Phase 4 run becomes `failed`, and the UI must surface both the top-level failure and any completed table outputs.
- If Supabase upload fails after local Parquet creation, the table should be marked failed and the error recorded.
- If ClickHouse write fails, the run should fail rather than silently pretending monitoring succeeded.
- If a run is already `running`, the start endpoint must reject a second concurrent start request.

## Testing Strategy

### Automated tests

- unit tests for the new customer-to-canonical-contact serializer
- unit tests for seeded fixture discovery and runner orchestration
- unit tests for patching `document.phase4` state through success and failure transitions
- dashboard endpoint tests for:
  - Phase 4 page load
  - start endpoint success
  - duplicate-start rejection
  - status endpoint responses
- integration-style tests with fake object storage, fake ClickHouse client, and fake onboarding store covering the full fixed demo flow

### Manual smoke test

With a real `.env` configured:

1. start the Mira dashboard app
2. open the JWT-scoped Phase 4 page
3. start the fixed demo run
4. verify real artifact uploads in the Supabase lake bucket
5. verify ClickHouse rows exist for the run
6. verify the page auto-refreshes and shows final status, links, and events

## Acceptance Criteria

- `seeds/samples/midlayer-csv/` contains a real fixed demo tenant fixture set, not just documentation.
- The Phase 4 package can ingest seeded `invoice`, `customer`, and `contact` CSVs end-to-end.
- `customer` is transformed into the canonical Contact target shape.
- The runner writes real Parquet and manifest artifacts to the configured Supabase S3-compatible bucket.
- The runner writes real telemetry rows to ClickHouse.
- The existing Mira dashboard app exposes a separate Phase 4 page and does not regress the original onboarding page.
- The Phase 4 page auto-refreshes while a run is active.
- The page shows overall status, per-table summaries, artifact links, and recent events/errors.
- Failures are persisted into `document.phase4` and surfaced in the UI.

## Out of Scope

- replacing the future Phase 3 validation loop trigger
- dataset selection from the UI
- charts, historical trends, or alerting
- a dedicated new Phase 4 control-plane table
- a separate standalone Phase 4 dashboard service

## Assumptions

- The real `.env` now contains the Supabase and ClickHouse values needed for the demo path.
- The missing `MIRA_JWT_SECRET` and `MIRA_DASHBOARD_BASE_URL` can be added before the manual smoke test if not already present in the actual runtime environment.
- Reusing `onboarding_runs.document.phase4` is acceptable as temporary control-plane state until Phase 3 integration exists.
