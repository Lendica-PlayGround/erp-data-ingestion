# Phase 4 / 5: Operational Storage, Observability, Validation, And Testing

**Date:** April 19, 2026  
**Scope:** Combined implementation-ready spec for Phase 4 and Phase 5. Phase 4 defines the operational data plane after Phase 3 loads canonical `mid_*` rows. Phase 5 defines the validation, reconciliation, replay, and testing system that determines whether those loads are trustworthy.  
**References:** `docs/0001-prd.md`, `docs/0002-phase1-midlayer-db-contract.md`, `docs/0003-phase2-3-midlayer-agent.md`, `.env`

---

## 1. Outcome

After Phases 4 and 5 are complete, the platform must:

1. Persist normalized `mid_*` rows and transformed `target_*` rows in Supabase Postgres as the operational source of truth.
2. Preserve replayable run artifacts in Supabase Storage via the S3-compatible endpoint.
3. Stream run telemetry, data-quality events, reconciliation summaries, and freshness metrics into ClickHouse for analytics and monitoring.
4. Detect and explain ingestion problems before bad data silently reaches downstream consumers.
5. Provide an implementation path that can be built incrementally, verified at each step, and reused across connectors.

## 2. Responsibilities By Phase

### 2.1 Phase 4

Phase 4 is the runtime data plane and observability layer after connector execution:

- Supabase Postgres stores connector configs, run metadata, normalized `mid_*` rows, approved `target_*` rows, and validation summaries.
- Supabase Storage stores replayable artifacts per run, including raw extracts, transformed CSVs, validation reports, and failure snapshots.
- ClickHouse stores analytics-grade telemetry for dashboards, anomaly detection, freshness monitoring, and operator investigation.
- Every sync remains replayable by batch. Corrections are represented by new runs and superseding records, not silent in-place mutation.

### 2.2 Phase 5

Phase 5 is the trust layer:

- Validate schema, type coercion, required fields, and key uniqueness before a batch is promoted.
- Reconcile source counts and monetary totals against `mid_*` and `target_*`.
- Detect freshness drift, null spikes, schema mismatches, and broken delta cursors.
- Make failures diagnosable with enough stored evidence to reproduce and fix them quickly.

## 3. Architecture

### 3.1 Canonical stores

| Layer | System | Purpose |
| :--- | :--- | :--- |
| Operational data | Supabase Postgres | Canonical `mid_*`, `target_*`, run metadata, loader state, validation summaries |
| Replay artifacts | Supabase Storage S3 gateway | Raw source dumps, mapped CSVs, reconciliation reports, failure bundles |
| Analytics and monitoring | ClickHouse Cloud | High-volume events, metrics, dashboards, anomaly and freshness queries |

### 3.2 Data flow

1. Phase 3 connector run pulls source data and transforms it into canonical mid-layer rows.
2. The run writes raw extracts and intermediate artifacts to Supabase Storage under a run-specific prefix.
3. The loader writes batch-stamped rows into `mid_*`.
4. Validation checks run against the staged batch.
5. If the batch passes, approved rows are transformed into `target_*`.
6. Run events, row counts, validation results, and reconciliation summaries are emitted to ClickHouse.
7. If the batch fails, the run is marked failed, artifacts stay replayable, and no promotion to `target_*` occurs.

### 3.3 Required identifiers

Every run and every promoted row must carry:

- `company_id`
- `run_id`
- `load_batch_id`
- `sync_type` with values `initial` or `delta`
- `mapping_version`
- `midlayer_schema_version`
- source identity fields from Phase 1 and Phase 3

These identifiers are the join keys across Postgres, Storage, and ClickHouse.

## 4. Environment Contract

The following environment values are required for Phase 4 and Phase 5 work in this repo.

### 4.0 Current implementation status

The current repo now implements the first Phase 4/5 execution slice in `mira/supabase/load_mid_from_mapper.py`:

- `MIRA_RUN_ID` is required before a load starts so every batch has stable lineage.
- Each loader run writes a JSON validation report before batch completion.
- Raw input, mapped CSV, validation report, and a manifest are uploaded to Supabase Storage through the S3-compatible endpoint.
- `ingestion_load_batches.metadata` is patched with durable storage keys plus a normalized `run_events` payload.
- Loader `run_events` are published into ClickHouse `run_events`.
- Any row-level validation failure causes the batch status to be marked `failed`, even if some rows were valid.
- The repo now includes `mira/supabase/load_target_from_mid.py`, which promotes `mid_*` rows into `target_*` tables for the currently supported relational contract.

This is not the full Phase 4/5 rollout yet:

- Only `run_events` are currently written to ClickHouse; validation, reconciliation, freshness, and anomaly tables are still future work.
- `target_*` promotion now exists as a runnable path, but reconciliation reports and richer gating are still future steps.
- Replay uses the stored artifact contract, but there is not yet a dedicated replay command.

### 4.1 ClickHouse analytics

```env
CLICKHOUSE_HOST=https://fvob11b0ny.us-east-1.aws.clickhouse.cloud
CLICKHOUSE_PORT=8443
CLICKHOUSE_USERNAME=default
CLICKHOUSE_PASSWORD=a6KRF2s33_POR
CLICKHOUSE_DATABASE=phase4
CLICKHOUSE_SECURE=true
```

Usage:

- Store run events, validation events, freshness metrics, anomaly summaries, and dashboard-facing aggregates.
- Use TLS for all connections.
- Treat this database as append-oriented analytics storage, not the operational write path.

### 4.2 Supabase Storage for replayable artifacts

```env
SUPABASE_STORAGE_S3_BUCKET=mira
SUPABASE_STORAGE_S3_ENDPOINT_URL=https://yyebwskrgbgczpnhayke.storage.supabase.co/storage/v1/s3
SUPABASE_STORAGE_S3_ACCESS_KEY_ID=c958793e3e65734ed17e42954333e1c2
SUPABASE_STORAGE_S3_SECRET_ACCESS_KEY=f22f33d35c879a73206ad8f50e3b393297594a20e1428890717518e37a8d32bc
SUPABASE_STORAGE_S3_REGION=us-east-1
```

Usage:

- Store raw extracts, normalized CSVs, rejected rows, validation reports, reconciliation reports, and replay manifests.
- Organize keys by `company_id/run_id/load_batch_id`.
- Never rely on local disk as the durable artifact store for completed runs.

## 5. Phase 4 Implementation Steps

This section is intentionally ordered so an engineer can implement it in sequence.

### Step 1: Define runtime metadata tables in Supabase Postgres

Deliverables:

- `onboarding_runs` remains the top-level run record from Phase 3.
- Add or finalize relational tables for:
  - `load_batches`
  - `validation_results`
  - `reconciliation_results`
  - `sync_cursors`
  - optional `artifact_manifest`

Minimum fields:

- `run_id`, `company_id`, `table_name`, `sync_type`, `status`
- counts for rows extracted, accepted, rejected, promoted
- timing fields for started, completed, and last successful sync
- references to artifact keys in Supabase Storage

Acceptance:

- A single query can answer: what ran, what loaded, what failed, and where the evidence is stored.

### Step 2: Define the artifact layout in Supabase Storage

Required key layout:

```text
mira/
  company_id=<company_id>/
    run_id=<run_id>/
      batch_id=<load_batch_id>/
        raw/
        mapped/
        rejects/
        validation/
        reconciliation/
        manifests/
```

Current implementation note:

- The loader already uploads `raw/`, `mapped/`, `validation/`, and `manifests/` artifacts for each batch.
- `rejects/` and `reconciliation/` are still planned but not yet produced by runtime code.

Required artifacts per batch:

- raw source payload or extracted file snapshot
- mapped mid-layer CSV or JSONL
- reject file for failed rows
- validation report
- reconciliation report
- manifest file with checksums and record counts

Acceptance:

- Any failed or successful batch can be replayed using only Postgres metadata plus the stored artifacts.

### Step 3: Add batch promotion flow from `mid_*` to `target_*`

Rules:

- Promotion only happens after validation passes.
- `target_*` rows retain lineage back to `mid_*` and `load_batch_id`.
- Replays produce a new batch record instead of mutating historical metadata.

Minimum promotion metadata:

- `source_mid_row_id`
- `source_load_batch_id`
- `target_loaded_at`
- `target_transform_version`

Acceptance:

- An operator can trace any target row back to the exact mid-layer batch and source artifact set.

### Step 4: Emit observability events to ClickHouse

Create append-only event streams for:

- run lifecycle events
- validation failures
- reconciliation summaries
- freshness measurements
- anomaly detections
- retry and replay events

Recommended logical tables:

- `run_events`
- `validation_events`
- `reconciliation_events`
- `freshness_events`
- `anomaly_events`

Minimum columns across event tables:

- `event_time`
- `company_id`
- `run_id`
- `load_batch_id`
- `table_name`
- `event_type`
- `severity`
- `payload_json`

Acceptance:

- A dashboard query can answer which companies are stale, which runs failed today, and which tables are drifting.

Current implementation note:

- The repo now creates normalized `run_events` payloads and stores them in batch metadata.
- The loader also publishes those events into ClickHouse `run_events`.

### Step 5: Standardize telemetry emission

Requirements:

- Wrap loader and validator execution in a shared telemetry contract.
- Emit start, success, fail, retry, and replay events consistently.
- Include latency, row counts, and validator outcomes in every run summary.

Preferred approach:

- Use OpenTelemetry-style spans and attributes in code, then write normalized analytics rows to ClickHouse.
- Keep the event schema stable even if the runtime transport changes later.

Acceptance:

- Metrics from different connectors are comparable without connector-specific query logic.

### Step 6: Add freshness and anomaly monitoring

Metrics to compute per `(company_id, table_name)`:

- last successful sync time
- expected sync cadence
- lag in minutes
- row-count delta versus prior run
- reject-rate percentage
- null-rate by important fields
- invoice monetary total drift

Initial anomaly rules:

- stale sync beyond expected SLA
- row count deviates beyond threshold
- null spike in required fields
- schema mismatch between expected and observed columns
- reconciliation mismatch for counts or money totals

Acceptance:

- A failed or suspicious run is visible in analytics without reading raw logs first.

## 6. Phase 5 Validation And Testing Steps

### Step 7: Add pre-promotion validation gates

Validation must execute after `mid_*` load and before `target_*` promotion.

Required checks:

- JSON Schema and model conformance
- required field presence
- type conversion success
- composite source identity uniqueness
- valid currency plus monetary pairing
- timestamp normalization to UTC
- `_unmapped` preservation for unsupported source columns

Failure behavior:

- mark batch as failed
- persist reject rows and a validation report
- emit failure events to ClickHouse
- do not promote to `target_*`

Current implementation note:

- The loader already writes a validation report and marks any mixed-validity batch as `failed`.
- Reject artifact uploads and dedicated ClickHouse failure-event tables are not wired yet.

### Step 8: Add reconciliation checks

Each run must produce reconciliation summaries for both source-to-mid and mid-to-target.

Required checks:

- extracted source row count versus loaded `mid_*` count
- validated `mid_*` count versus promoted `target_*` count
- source invoice totals versus normalized invoice totals after cents-to-dollars conversion
- duplicate key detection across delta sync boundaries

Stripe-specific rule:

- For invoice data, the reconciliation report must explicitly show minor-unit to major-unit normalization and verify that totals match expected decimal values.

### Step 9: Add replay and failure-bundle support

For any failed batch, the system must preserve enough evidence to replay deterministically.

Failure bundle contents:

- raw source artifact
- mapped artifact
- reject rows
- validator outputs
- environment-independent manifest of file hashes and record counts

Acceptance:

- An engineer can rerun the exact failed batch without asking the customer to resend the source dataset.

### Step 10: Build the test suite in layers

Unit tests:

- field coercion
- cents-to-dollars conversion
- timestamp normalization
- uniqueness and dedupe helpers
- anomaly rule evaluation

Integration tests:

- load a batch into `mid_*`
- run validation
- promote into `target_*`
- emit ClickHouse events
- upload artifacts to Supabase Storage

Replay tests:

- rerun a stored failed batch from artifact manifest
- confirm deterministic validator output

Reconciliation tests:

- source counts match `mid_*`
- `mid_*` matches `target_*`
- invoice totals remain stable after normalization

Smoke tests:

- one initial sync
- one delta sync
- one forced failure with replay

### Step 11: Add release gates

Before declaring Phase 4/5 complete, all of the following must be true:

1. A successful initial sync writes artifacts to Supabase Storage, rows to `mid_*` and `target_*`, and events to ClickHouse.
2. A successful delta sync updates cursors and produces reconciliation output.
3. A failed validation blocks promotion and leaves a replayable failure bundle.
4. ClickHouse can report stale companies, failed runs, and anomaly counts.
5. Stripe invoice tests prove cents-to-dollars normalization and invoice-total reconciliation.

## 7. Definition Of Done

Phase 4 and Phase 5 are done when:

- Supabase Postgres is the operational source of truth for normalized and target data.
- Supabase Storage is the durable replay store for run artifacts.
- ClickHouse is populated with actionable monitoring data.
- Validation gates prevent bad batches from being promoted.
- Replay works from stored artifacts.
- The test suite covers unit, integration, replay, reconciliation, and smoke paths.

## 8. Recommended Build Order

Implement in this order:

1. Postgres metadata tables
2. Storage artifact layout and manifest writing
3. Validation result persistence
4. `mid_*` to `target_*` promotion gating
5. ClickHouse event ingestion
6. Reconciliation reports
7. Freshness and anomaly rules
8. Replay tooling
9. Full integration and smoke coverage

This order gives a usable operational path early, then layers trust and monitoring on top without blocking basic ingestion progress.
