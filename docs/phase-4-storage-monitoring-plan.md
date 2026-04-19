# Phase 4: Lake Storage, Execution, and Monitoring

## Summary
Phase 4 should separate three concerns instead of treating ClickHouse, Supabase, and Nebius as interchangeable:

- Phase 4 consumes the validated mid-layer outputs produced by Phases 1 through 3 rather than pulling directly from source ERPs.
- Supabase Storage via its S3-compatible endpoint is the durable landing zone for raw files, standardized outputs, and replayable run artifacts.
- Supabase Postgres is the control plane for run metadata, schema versions, mappings, approvals, and validation state.
- ClickHouse is the analytics and observability layer for ingestion telemetry, validation anomalies, and monitoring queries.
- The canonical storage schemas are based on Merge common-model objects, but Merge is not used as a runtime dependency or integration service in Phase 4.

## Upstream Contract From Earlier Phases
Phase 4 depends on the outputs of the earlier PRD phases and should treat them as fixed handoff contracts:

- Phase 1 defines the mid-layer schema contract, versioned schemas, and the strict CSV layout and naming rules in the Supabase `midlayer-csv` bucket.
- Phase 2 produces the exploration and schema-understanding artifacts: table summaries, field descriptions, domains, units, datasource notes, and pull-process guidance.
- Phase 3 runs the generic Python ingestion runner on a schedule, reads per-company connector config, pulls source records through a uniform connector interface, applies the mapping artifact, writes standardized CSV outputs to Supabase, and emits run logs and row counts.

Phase 4 starts after those standardized mid-layer files exist and focuses on durable lake storage, target-schema persistence, observability, and replayability.

## Recommended Stack

### 1. Lake Storage
Use a dedicated Supabase Storage bucket, accessed through the S3-compatible endpoint, as the canonical lake destination.

- Store append-only standardized records.
- Keep historical initial and delta outputs.
- Preserve replayability by never mutating prior run artifacts.
- Persist records in your own storage layer using Merge-aligned object shapes.
- Treat the Supabase `midlayer-csv` bucket as the upstream handoff layer, and use a separate Phase 4 lake bucket for long-term artifacts.

### 2. Control Plane
Use Supabase Postgres for operational metadata.

Store:

- connector definitions
- company/source configuration
- schema versions
- mapping versions
- run registry
- validation summaries
- anomaly status
- object storage paths
- human approvals

### 3. Analytics and Monitoring
Use ClickHouse for:

- run-level metrics
- throughput and latency analysis
- failure/event logging
- data quality anomaly tracking
- freshness monitoring
- dashboards and alert query backends

## Canonical Business Objects
Phase 4 should standardize stored ERP data around Merge-aligned business objects while remaining independent from Merge as a product dependency.

- `Invoice` object for invoice and billing records stored in the lake
- `Contact` object for customer and contact records associated with each client's ERP system

These are schema references only. The system should not call Merge APIs or require Merge as a dependency during ingestion, storage, or monitoring.

Relationship to the earlier phases:

- Phase 1 may still refer to `invoice`, `customer`, and `contact` tables in the mid-layer contract.
- In Phase 4 storage, customer-like and contact-like entities should be persisted in the canonical `Contact` object shape unless a later schema split is explicitly introduced.
- This keeps the target lake simpler while preserving compatibility with the earlier onboarding and mapping flow.

### Invoice Storage Object
Use the Merge `Invoice` object shape as the canonical invoice record contract.

Minimum fields to preserve in storage:

- object identifiers: internal record ID, source `remote_id`, invoice `number`
- relationship fields: `contact`, `company`
- lifecycle dates: `issue_date`, `due_date`, `paid_on_date`, `remote_updated_at`
- money fields: `currency`, `exchange_rate`, `sub_total`, `total_tax_amount`, `total_discount`, `total_amount`, `balance`
- state fields: `type`, `status`, `memo`, `remote_was_deleted`
- nested detail: `line_items`
- source-extension fields: `remote_data`, `remote_fields`, `field_mappings`

### Contact Storage Object
Use the Merge `Contact` object shape as the canonical contact/customer record contract.

Minimum fields to preserve in storage:

- object identifiers: internal record ID, source `remote_id`
- business identity: `name`, `email_address`, `tax_number`
- customer/supplier flags: `is_customer`, `is_supplier`
- lifecycle/state: `status`, `currency`, `remote_updated_at`, `remote_was_deleted`
- ownership: `company`
- nested detail: `addresses`, `phone_numbers`
- source-extension fields: `remote_data`, `remote_fields`, `field_mappings`

For the MVP, contacts should primarily represent customer-side ERP entities linked to invoices, even though the canonical schema can also represent suppliers/vendors.

## Execution Flow
1. Phase 3 runs a generic Python ingestion worker on Nebius compute for each `(company, table)` sync.
2. The worker reads per-company connector configuration and the approved mapping artifact produced by the earlier phases.
3. The worker writes standardized mid-layer CSV outputs into the Supabase `midlayer-csv` bucket using the agreed naming convention.
4. Phase 4 reads those standardized mid-layer outputs and converts them into canonical `Invoice` and `Contact` storage objects.
5. Phase 4 writes append-only lake outputs into the dedicated Supabase Storage lake bucket.
6. The run writes metadata, config pointers, schema versions, and validation summaries into Supabase Postgres.
7. The run emits logs, metrics, traces, and validation events into the observability pipeline.
8. Observability data lands in ClickHouse for dashboards, anomaly detection, alert evaluation, and root-cause analysis.

## Data Lake Design
Preferred lake file format:

- Parquet for Phase 4 storage
- CSV may still exist earlier in onboarding/debug flows, but Phase 4 should prefer columnar storage

Partitioning convention:

- `company_id=<id>/table=<table>/sync_type=<initial|delta>/date=<YYYY-MM-DD>/run_id=<id>/`

Write model:

- append-only files
- immutable run outputs
- corrections happen through new runs, not in-place edits

Schema model:

- versioned canonical schemas for `invoice` and `contact`
- lake records must preserve the Merge-aligned common fields for those objects
- preserve unmapped source fields in an `extras`, `remote_data`, or `remote_fields` structure instead of dropping them

Storage mapping rules:

- every source invoice record maps into one canonical `Invoice` object
- every source customer or contact record maps into one canonical `Contact` object
- invoice records should link to contact records through the canonical contact identifier
- source-specific fields that do not cleanly map to the canonical object should still be retained for replay, audit, and future schema evolution
- the Phase 1 CSV contract and the Phase 4 target-lake contract should be versioned independently so the handoff can evolve safely

## Monitoring Design

### Pipeline Monitoring
Track:

- run success/failure
- retries
- run duration
- bytes processed
- rows processed
- backlog
- last successful sync
- scheduler health

### Data Quality Monitoring
Track:

- row-count drift
- null-rate spikes
- duplicate identifiers
- schema mismatches
- invalid monetary formatting
- stale data / freshness lag
- source-to-lake reconciliation failures

## Observability Stack
Use OpenTelemetry instrumentation in workers and schedulers.

Recommended flow:

- workers emit logs, metrics, and traces
- OpenTelemetry Collector receives and routes telemetry
- infra metrics come from the compute platform's monitoring layer
- ClickHouse stores deep operational telemetry
- Grafana or equivalent alerting evaluates alert rules and notifies Slack or email

## Dashboards
Required dashboards:

- Run Overview
- Data Quality
- Connector Health
- Cost and Volume

## Acceptance Criteria
- Phase 4 consumes valid outputs from the Phase 1 schema contract and the Phase 3 generic Python runner without redefining the upstream handoff format.
- Initial and delta syncs both land standardized files in object storage.
- Stored records conform to the canonical `Invoice` and `Contact` object contracts.
- Every run creates a metadata record in Supabase.
- Every run emits telemetry to the monitoring pipeline.
- Failed runs do not corrupt previous data.
- Monitoring detects failed jobs, stale syncs, row-count anomalies, schema mismatches, and null-rate spikes.
- Stripe MVP validates cents-to-dollars normalization and invoice consistency.

## Final Recommendation
For Phase 4:

- Use Nebius for compute.
- Use Supabase Storage for Phase 4 lake artifacts.
- Use Supabase for metadata and workflow control state.
- Use ClickHouse for analytics and monitoring.

Do not choose a single product for all three roles.
