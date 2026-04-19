# Phase 1: Mid-Layer Database Contract & Seed Data Blueprint

**Date:** April 18, 2026
**Scope:** Seed data setup, mid-layer dataset uniform format (merge.dev-aligned), and Supabase Postgres storage targets for `mid_*` and `target_*` tables.
**References:** `docs/0001-prd.md`, `docs/discussion/initial-discussion.md`

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
- **Golden expected outputs**: for each seed, hand-curate the expected normalized records so the mapping agent has a pass/fail target for the `mid_*` tables.

## 2. Mid-Layer Uniform Schema (merge.dev-aligned)

- **Adopt merge.dev Accounting/CRM Common Models as the canonical schema** for the three MVP tables:
  - `Invoice` → merge.dev Accounting `Invoice` object
  - `Customer` → merge.dev Accounting `Contact` (or `Customer` depending on category) object
  - `Contact` → merge.dev CRM `Contact` object
- **Publish schemas as versioned JSON Schema / Pydantic models** in `midlayer-schema-guide/midlayer/v1/{invoice,customer,contact}.schema.json` — single source of truth for validation.
- **Normalize the known Stripe pain points at this layer**:
  - All monetary fields stored as `DECIMAL(18,4)` in major units (dollars) — never cents. Mapping layer divides by 100 for Stripe.
  - Currency code stored as separate ISO-4217 field (`currency`).
  - Invoice IDs stored raw with original prefix preserved (e.g. `in_1Abc...`), plus a normalized `external_id` field.
  - All timestamps in ISO 8601 UTC.
  - Decimal separator always `.`, thousands separator never present.
- **"Other" fallback column per table**: `_unmapped` (`jsonb`) to preserve any source columns the agent couldn't map — satisfies the PRD's no-data-loss requirement.
- **Required metadata columns on every mid-layer row**:
  - `_source_system`, `_source_record_id`, `_company_id`, `_ingested_at`, `_source_file`, `_mapping_version`, `_row_hash`

## 3. Storage Target — Supabase Postgres

- **Canonical tables**:
  - `mid_invoices`, `mid_customers`, `mid_contacts`
  - `target_invoices`, `target_customers`, `target_contacts`
- **Table role**:
  - `mid_*` stores the canonical source-neutral row contract as closely as possible to the mid-layer schema.
  - `target_*` stores the transformed downstream shape plus lineage back to `mid_*`.
- **Batching convention**:
  - Every load should record `load_batch_id`, `sync_type` (`initial` or `delta`), and ingestion timestamps so replays and audits stay simple.
- **Identity convention**:
  - Preserve source identity in `external_id`, `_source_record_id`, `_source_system`, and `_company_id`.
  - Enforce composite uniqueness on `(_source_system, _source_record_id, _company_id)` for `mid_*`.

## 4. Row Contract Spec (strict, enforced)

- **Types**:
  - Money: `DECIMAL(18,4)` in major units.
  - Booleans: native Postgres `boolean`.
  - Timestamps: `timestamptz` in UTC.
  - JSON-valued fields such as `_unmapped`, `addresses`, `email_addresses`, `phone_numbers`: `jsonb`.
- **Column order** in docs mirrors the canonical schema, but relational consumers should rely on explicit column names rather than positional order.
- **Null representation**: use SQL `NULL`, not string sentinels like `NULL`, `NaN`, or `None`.

## 5. Validation Gate Before Insert

- **Schema validation** against the Pydantic/JSON Schema model before insert; failures routed to reject tables or validation logs.
- **Assertion checks**:
  - Row count matches source extraction count (minus documented rejects).
  - No NaN / null in non-nullable fields.
  - Currency-bearing rows have both amount and currency populated.
  - Primary key (`_source_record_id` + `_source_system` + `_company_id`) unique within each canonical table.
- **Record a load batch row** only after all checks pass; this is the signal downstream loaders listen on.

## 6. Deliverables for Phase 1 (Definition of Done)

- [ ] `midlayer-schema-guide/midlayer/v1/` committed with Invoice, Customer, Contact JSON Schemas.
- [ ] `seeds/` folder with Stripe + Google Sheets samples and golden expected outputs.
- [ ] `midlayer-schema-guide/midlayer-db-spec.md` documenting table/column/validation rules above.
- [ ] Reference mapper for Stripe → `mid_*` rows that passes all seed goldens.
- [ ] Sample `mid_*` and `target_*` rows loaded into Supabase Postgres for one test company.
