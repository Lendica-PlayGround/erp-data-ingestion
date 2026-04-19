# Mid-Layer CSV Spec (v1)

**Status:** authoritative for Phase 1 mapper output and the Phase 3 loader contract.

**Companion docs (read together):**
- `mira/midlayer-schema-guide/midlayer-schema-guide.md` — row semantics, types, enums, merge.dev alignment.
- `mira/midlayer/v1/*.schema.json` — machine-checkable field contract.
- `seeds/samples/midlayer-csv/` — worked example of everything on this page.

## 1. Bucket & paths

- **Bucket:** `midlayer-csv` (Supabase Storage in production; a local mirror under
  `./output/midlayer-csv/` for seeds/dev runs).
- **Layout** (partitioned for efficient delta + Phase 3 loading):

```
midlayer-csv/
  <company_id>/
    <table>/                                # invoices | customers | contacts
      initial/
        <company_id>_<table>_initial_<YYYYMMDD>.csv
        <company_id>_<table>_initial_<YYYYMMDD>.csv.meta.json
      delta/
        dt=<YYYY-MM-DD>/
          <company_id>_<table>_delta_<YYYYMMDD>_<run_id>.csv
          <company_id>_<table>_delta_<YYYYMMDD>_<run_id>.csv.meta.json
      _manifest/
        <YYYY-MM-DD>.json                    # run metadata, row counts, checksums
      _rejects/
        dt=<YYYY-MM-DD>/<run_id>.csv         # rows that failed validation
        dt=<YYYY-MM-DD>/<run_id>.errors.jsonl
```

- **File naming:** `<company_id>_<table>_<initial|delta>_<YYYYMMDD>[_<run_id>].csv`.
  Sortable lexicographically, idempotent, traceable back to one Airflow DAG run.
  `run_id` is the Airflow `run_id` (or a ULID for local runs).

## 2. CSV file format (strict, enforced)

| Concern | Rule |
| :--- | :--- |
| Encoding | UTF-8, **BOM-less** |
| Delimiter | `,` (ASCII 0x2C) — no regional variants |
| Quoting | `csv.QUOTE_MINIMAL` (RFC 4180), double-quote as escape |
| Line terminator | `\n` (LF) — never CRLF |
| Header | Always present, `snake_case`, exact order of `schemas.midlayer.v1.models.{INVOICE,CUSTOMER,CONTACT}_COLUMNS` |
| Null | Empty string — never `NULL`, `NaN`, or `None` |
| Booleans | Lowercase `true` / `false` |
| Money | Plain decimal string, **exactly 4 decimal places**, no symbols/commas (`1250.0000`). Unknown → empty string. |
| Exchange rate | Plain decimal string, unitless ratio; precision preserved from source. Not subject to the 4-decimal rule. |
| Timestamps | ISO 8601 UTC with `Z` suffix (`2024-04-01T00:00:00Z`). Unknown → empty string. |
| JSON cells | `_unmapped`, `addresses`, `email_addresses`, `phone_numbers` — minified JSON with keys alphabetically sorted. Absent sub-fields are omitted (not `null`). |

## 3. Metadata columns (every row, every table)

All eight columns below are **always emitted** (the writer never omits a column). The "Required non-null" column distinguishes which cells may be empty.

| Column | Required non-null | Meaning |
| :--- | :---: | :--- |
| `_source_system` | ✔ | Slug of source system (`stripe`, `google_sheets`, …) |
| `_source_record_id` | ✔ | Raw source row id before normalization |
| `_company_id` | ✔ | Internal tenant id |
| `_ingested_at` | ✔ | ISO 8601 UTC timestamp of the ingestion run (stamped once per run) |
| `_source_file` | ✔ | Repo-relative path (or connector-job URI) of the source for this row |
| `_mapping_version` | ✔ | Semver of the mapping artifact (e.g. `stripe.invoice@0.1.0`) |
| `_row_hash` | ✔ | SHA-256 hex of the canonicalized mapped row — see schema guide §7.1 |
| `_unmapped` | — | Minified JSON of source columns the mapper couldn't map. `{}` or empty string when none. Cell is nullable; the column is always present. |

## 4. Sidecar `.meta.json`

For every `*.csv` emitted there MUST be a companion `*.csv.meta.json`:

```json
{
  "schema_version": "v1",
  "table": "invoices",
  "company_id": "acme-co",
  "source_system": "stripe",
  "sync_type": "initial",
  "run_id": "01HVA...",
  "source_run_id": "airflow:stripe_invoices_initial__2024-04-01",
  "mapping_version": "stripe.invoice@0.1.0",
  "generated_at": "2024-04-01T00:00:15Z",
  "row_count": 3,
  "reject_count": 0,
  "sha256": "<sha256 of the csv bytes on disk>"
}
```

## 5. `_manifest/<YYYY-MM-DD>.json`

Emitted **only after all validation passes**. This is the signal Phase 3 listens on.

```json
{
  "schema_version": "v1",
  "run_date": "2024-04-01",
  "run_id": "01HVA...",
  "company_id": "acme-co",
  "generated_at": "2024-04-01T00:00:25Z",
  "runs": [
    {
      "table": "invoices",
      "sync_type": "initial",
      "file": "acme-co/invoices/initial/acme-co_invoices_initial_20240401.csv",
      "sha256": "...",
      "row_count": 3,
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

## 6. Validation gate (runs before any write to `initial/` or `delta/`)

1. **Schema validation** via the v1 Pydantic models. Rows that fail → routed to
   `_rejects/dt=<YYYY-MM-DD>/<run_id>.csv` with a matching
   `<run_id>.errors.jsonl` (one JSON object per reject: `{row_index, field,
   error, source_record_id}`).
2. **Assertion checks** (fail the run, not just a row):
   - Row count in mid-layer CSV matches `source_rows - rejects`.
   - No nulls in non-nullable fields (`external_id` and all metadata).
   - Every row with a populated money column also has a populated `currency`.
   - Primary key `(_source_system, _source_record_id, _company_id)` is unique
     within the file.
3. **Manifest emit.** Only on full pass. Partial files are deleted if an assertion
   check trips between the row-level write and the manifest.

## 7. Initial vs delta semantics

- **Initial sync** produces exactly one `initial/<...>.csv` per (company, table)
  per onboarding. Full historical backfill. Idempotent by filename — re-running
  overwrites (after moving the prior file to `_archive/`, not part of v1).
- **Delta sync** produces at most one `delta/dt=<date>/<...>.csv` per (company,
  table, run). Cursor strategy:
  - Stripe: `created[gte]=<last_max_created>` with overlap by 1 hour.
  - Google Sheets: full read + `_row_hash` diff against the prior run.
- Rows with a `_row_hash` already seen in `initial/` **or** earlier `delta/`
  files for the same (company, table) are dropped at the writer. This gives
  append-only delta semantics with natural dedupe.

## 8. Change control

- Bumping any schema requires a new subfolder in `schemas/midlayer/vN/`. The
  bucket path stays the same; consumers pin `schema_version` per row via the
  sidecar.
- Breaking changes (renamed/removed columns) always bump the `vN` — additive
  changes (new nullable field) may stay on `v1` with a bumped `mapping_version`.
