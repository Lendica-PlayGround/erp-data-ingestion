# Mid-Layer Database Spec (v1)

**Status:** authoritative for Phase 1 mapper output and the Phase 3 loader contract.

**Companion docs (read together):**
- `midlayer-schema-guide/midlayer-schema-guide.md` — row semantics, types, enums, merge.dev alignment.
- `midlayer-schema-guide/midlayer/v1/*.schema.json` — machine-checkable field contract.
- `seeds/samples/midlayer-csv/` — historical fixture examples from the earlier CSV-first contract.

## 1. Tables & load metadata

- **Database:** Supabase Postgres.
- **Canonical tables:**
  - `mid_invoices`, `mid_customers`, `mid_contacts`
  - `target_invoices`, `target_customers`, `target_contacts`
- **Recommended supporting tables:**
  - `ingestion_load_batches`
  - `ingestion_validation_failures`
- **Batch fields:** every inserted row should carry enough metadata to trace a load, typically `load_batch_id`, `sync_type`, `inserted_at`, and lineage back to source identifiers.

## 2. Database row format (strict, enforced)

| Concern | Rule |
| :--- | :--- |
| Null | SQL `NULL` — never string sentinels like `NULL`, `NaN`, or `None` |
| Booleans | Native `boolean` |
| Money | `numeric(18,4)` in major units |
| Exchange rate | `numeric` with source-preserved precision |
| Timestamps | `timestamptz` normalized to UTC |
| JSON fields | `_unmapped`, `addresses`, `email_addresses`, `phone_numbers` stored as `jsonb` |

## 3. Metadata columns (every row, every table)

All eight columns below are always emitted on the canonical `mid_*` tables. The "Required non-null" column distinguishes which cells may be empty.

| Column | Required non-null | Meaning |
| :--- | :---: | :--- |
| `_source_system` | ✔ | Slug of source system (`stripe`, `google_sheets`, …) |
| `_source_record_id` | ✔ | Raw source row id before normalization |
| `_company_id` | ✔ | Internal tenant id |
| `_ingested_at` | ✔ | UTC timestamp of the ingestion run (stamped once per run) |
| `_source_file` | ✔ | Repo-relative path (or connector-job URI) of the source for this row |
| `_mapping_version` | ✔ | Semver of the mapping artifact (e.g. `stripe.invoice@0.1.0`) |
| `_row_hash` | ✔ | SHA-256 hex of the canonicalized mapped row — see schema guide §7.1 |
| `_unmapped` | — | JSON of source columns the mapper couldn't map. `{}` or `NULL` when none. Column remains present on every `mid_*` table. |

## 4. `ingestion_load_batches`

Every successful load should produce one batch row:

```json
{
  "load_batch_id": "01HVA...",
  "schema_version": "v1",
  "table_name": "mid_invoices",
  "company_id": "acme-co",
  "source_system": "stripe",
  "sync_type": "initial",
  "source_run_id": "airflow:stripe_invoices_initial__2024-04-01",
  "mapping_version": "stripe.invoice@0.1.0",
  "started_at": "2024-04-01T00:00:15Z",
  "completed_at": "2024-04-01T00:00:25Z",
  "row_count": 3,
  "reject_count": 0,
  "status": "succeeded"
}
```

## 5. `ingestion_validation_failures`

Rejects should be recorded in a table rather than sidecar files:

```json
{
  "load_batch_id": "01HVA...",
  "table_name": "mid_invoices",
  "row_index": 14,
  "field": "currency",
  "source_record_id": "in_123",
  "error": "currency must match ^[A-Z]{3}$",
  "created_at": "2024-04-01T00:00:18Z"
}
```

## 6. Validation gate (runs before any insert into `mid_*` or transform into `target_*`)

1. **Schema validation** via the v1 Pydantic models. Rows that fail go to `ingestion_validation_failures`.
2. **Assertion checks** (fail the run, not just a row):
   - Row count in `mid_*` matches `source_rows - rejects`.
   - No nulls in non-nullable fields (`external_id` and all metadata).
   - Every row with a populated money column also has a populated `currency`.
   - Primary key `(_source_system, _source_record_id, _company_id)` is unique within each canonical table.
3. **Batch completion.** Only mark the load batch successful on full pass.

## 6.1 Current loader entrypoint

The current repo entrypoint for loading canonical mid-layer rows is:

```bash
python3 mira/supabase/load_mid_from_mapper.py --input /path/to/source.csv --table invoices
```

What it does:

1. Executes the generated `phase2.5/output/handshake_run_mapper.py` script for the requested table.
2. Reads the resulting `*_mapped.csv` output in canonical mid-layer column order.
3. Creates an `ingestion_load_batches` row.
4. Records row-level parse failures in `ingestion_validation_failures`.
5. Upserts valid rows into `mid_customers`, `mid_contacts`, or `mid_invoices`.

The script can also read its defaults from repo-root `.env`:

- `MID_LOADER_INPUT_PATH`
- `MID_LOADER_TABLE`
- `MID_LOADER_MAPPER_PATH`
- `MID_LOADER_SYNC_TYPE`

## 7. Initial vs delta semantics

- **Initial sync** produces one or more batch-stamped inserts into `mid_*` per (company, table) onboarding. Full historical backfill.
- **Delta sync** produces incremental batch-stamped inserts into `mid_*`. Cursor strategy:
  - Stripe: `created[gte]=<last_max_created>` with overlap by 1 hour.
  - Google Sheets: full read + `_row_hash` diff against the prior run.
- Rows with a `_row_hash` already seen in earlier loads for the same (company, table) are dropped at the writer. This gives append-only delta semantics with natural dedupe.

## 8. Change control

- Bumping any schema requires a new subfolder in `schemas/midlayer/vN/`. The table family stays the same; consumers pin `schema_version` per row or per load batch.
- Breaking changes (renamed/removed columns) always bump the `vN` — additive changes (new nullable field) may stay on `v1` with a bumped `mapping_version`.
