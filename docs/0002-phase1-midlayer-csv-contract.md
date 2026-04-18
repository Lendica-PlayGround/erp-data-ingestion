# Phase 1: Mid-Layer CSV Contract & Seed Data Blueprint

**Date:** April 18, 2026
**Scope:** Seed data setup, mid-layer dataset uniform format (merge.dev-aligned), and CSV storage target (folder + file format).
**References:** `docs/0001-prd-draft.md`, `docs/discussion/initial-discussion.md`

---

## 1. Seed Data (Test-Driven Onboarding Input)

- **Pick one anchor source per table**: Stripe CSV exports for `Invoices` and `Customers`; a Google Sheet sample for `Contacts` (covers the "messy header row" edge case called out in the PRD).
- **Seed size**: 3 historical records per table per company (per PRD onboarding flow), plus 1 "dirty" sample per source (cents-based amounts, missing columns, extra columns, non-UTF-8 chars, European decimal separators).
- **Folder layout for seeds**:
  ```
  seeds/
    <source_system>/<company_id>/<table>/sample_<n>.{csv,json}
    seeds/<source_system>/<company_id>/README.md   # source, credentials ref, known quirks
  ```
- **Manifest file** (`seeds/manifest.yaml`): lists each seed with `source`, `table`, `record_count`, `expected_unified_rows`, and `known_edge_cases` — used as the TDD fixture set for the mapping agent.
- **Golden expected outputs**: for each seed, hand-curate the expected mid-layer CSV output (`seeds/.../expected/<table>.csv`) so the mapping agent has a pass/fail target.

## 2. Mid-Layer Uniform Schema (merge.dev-aligned)

- **Adopt merge.dev Accounting/CRM Common Models as the canonical schema** for the three MVP tables:
  - `Invoice` → merge.dev Accounting `Invoice` object
  - `Customer` → merge.dev Accounting `Contact` (or `Customer` depending on category) object
  - `Contact` → merge.dev CRM `Contact` object
- **Publish schemas as versioned JSON Schema / Pydantic models** in `schemas/midlayer/v1/{invoice,customer,contact}.schema.json` — single source of truth for validation.
- **Normalize the known Stripe pain points at this layer** (from the discussion):
  - All monetary fields stored as `DECIMAL(18,4)` **in major units (dollars)** — never cents. Mapping layer divides by 100 for Stripe.
  - Currency code stored as separate ISO-4217 field (`currency`).
  - Invoice IDs stored raw with original prefix preserved (e.g., `in_1Abc...`), plus a normalized `external_id` field.
  - All timestamps in **ISO 8601 UTC** (`YYYY-MM-DDTHH:MM:SSZ`).
  - Decimal separator always `.`, thousands separator never present.
- **"Other" fallback column per table**: `_unmapped` (JSON blob) to preserve any source columns the agent couldn't map — satisfies the PRD's no-data-loss requirement.
- **Required metadata columns on every mid-layer row**:
  - `_source_system`, `_source_record_id`, `_company_id`, `_ingested_at`, `_source_file`, `_mapping_version`, `_row_hash`.

## 3. Storage Target — CSV Layout on Supabase

- **Bucket**: `midlayer-csv` (Supabase Storage, per PRD tech stack).
- **Folder structure** (partitioned for efficient delta + Phase 3 loading):
  ```
  midlayer-csv/
    <company_id>/
      <table>/                         # invoices | customers | contacts
        initial/
          <company_id>_<table>_initial_<YYYYMMDD>.csv
        delta/
          dt=<YYYY-MM-DD>/
            <company_id>_<table>_delta_<YYYYMMDD>_<run_id>.csv
        _manifest/
          <YYYY-MM-DD>.json            # run metadata, row counts, checksums
        _rejects/
          dt=<YYYY-MM-DD>/<run_id>.csv # rows that failed validation
  ```
- **File naming convention**: `<company_id>_<table>_<initial|delta>_<YYYYMMDD>[_<run_id>].csv` — sortable, idempotent, traceable back to an Airflow DAG run.

## 4. CSV File Format Spec (strict, enforced)

- **Encoding**: UTF-8, BOM-less.
- **Delimiter**: `,` (comma). No regional variants.
- **Quoting**: `QUOTE_MINIMAL` (RFC 4180), double-quote as escape.
- **Line terminator**: `\n` (LF).
- **Header**: always present, snake_case, matches mid-layer schema field order exactly.
- **Null representation**: empty string (never `NULL`, `NaN`, or `None`).
- **Types & formats**:
  - Money: plain decimal string, no symbols/commas (`1234.56`).
  - Booleans: `true` / `false` lowercase.
  - Timestamps: ISO 8601 UTC with `Z` suffix.
  - JSON-valued cells (the `_unmapped` column): minified JSON, double-quoted.
- **Companion sidecar** per CSV: `<same_name>.meta.json` containing `schema_version`, `row_count`, `sha256`, `source_run_id`, `mapping_version`, `generated_at` — enables the Phase 3 loader and monitoring layer to verify integrity.

## 5. Validation Gate Before Write

- **Schema validation** against the Pydantic/JSON Schema model; failures routed to `_rejects/`.
- **Assertion checks** (aligns with PRD §4 Observability):
  - Row count matches source extraction count (minus documented rejects).
  - No NaN / null in non-nullable fields.
  - Currency-bearing rows have both amount and currency populated.
  - Primary key (`_source_record_id` + `_source_system` + `_company_id`) unique within file.
- **Emit `_manifest/<date>.json`** only after all checks pass; this is the signal Phase 3 listens on.

## 6. Deliverables for Phase 1 (Definition of Done)

- [ ] `schemas/midlayer/v1/` committed with Invoice, Customer, Contact JSON Schemas.
- [ ] `seeds/` folder with Stripe + Google Sheets samples and golden expected outputs.
- [ ] `docs/midlayer-csv-spec.md` documenting folder/file/format rules above.
- [ ] Reference mapper for Stripe → mid-layer CSV that passes all seed goldens.
- [ ] Sample `initial/` and `delta/` CSVs + manifests uploaded to Supabase `midlayer-csv` bucket for one test company.
