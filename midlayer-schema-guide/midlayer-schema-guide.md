# Mid-Layer Uniform Schema Guide (v1)

## **Date:** April 18, 2026

## 1. Goal & naming convention

The mid-layer uses **[merge.dev](https://docs.merge.dev/) Common Models** as the canonical vocabulary for cross-source ERP data. All three MVP tables follow merge.dev naming, casing (`snake_case`), enum values, and type conventions verbatim, so that a mapping authored against merge.dev's docs will drop into our pipeline with zero renaming.


| Mid-layer table | merge.dev common model                                                | Reference                                                                                                                                                  |
| --------------- | --------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `invoices`      | Accounting → **Invoice**                                              | [https://docs.merge.dev/merge-unified/accounting/common-models/invoices/list](https://docs.merge.dev/merge-unified/accounting/common-models/invoices/list) |
| `customers`     | Accounting → **Contact** (entities classified as customers/suppliers) | [https://docs.merge.dev/merge-unified/accounting/common-models/contacts/list](https://docs.merge.dev/merge-unified/accounting/common-models/contacts/list) |
| `contacts`      | CRM → **Contact** (individual people)                                 | [https://docs.merge.dev/merge-unified/crm/common-models/contacts/list](https://docs.merge.dev/merge-unified/crm/common-models/contacts/list)               |


Two distinct merge.dev models share the label "Contact", so we disambiguate:

- `**customers`** = merge.dev *Accounting* Contact. A billable entity (company or person acting as a customer/vendor). Used by invoices.
- `**contacts*`* = merge.dev *CRM* Contact. An individual person tied to an account (sales/CRM relationships).

## 2. Sources of truth

The **JSON Schemas are the contract**. Pydantic models and this markdown must track them. See §9 for precedence when the three disagree.

```
midlayer-schema-guide/midlayer/v1/
  invoice.schema.json    ← canonical path (Accounting Invoice)
  customer.schema.json   ← canonical path (Accounting Contact)
  contact.schema.json    ← canonical path (CRM Contact)
  models.py              ← Pydantic v2 mirrors + canonical column order
```

- **Schema draft:** JSON Schema 2020-12, `additionalProperties: false`.
- **Required non-null on every row (all tables):** `external_id`, and the 7 metadata fields — `_source_system`, `_source_record_id`, `_company_id`, `_ingested_at`, `_source_file`, `_mapping_version`, `_row_hash`.
- **Always-present columns (header order), not required to be non-null:** `_unmapped` (may be empty string / `{}` / a minified JSON object), `remote_was_deleted` (defaults to `false`), and every nullable public field for that table.
- **Field order** in the CSV header is defined by `models.INVOICE_COLUMNS` / `CUSTOMER_COLUMNS` / `CONTACT_COLUMNS`. Never reorder at the writer.

## 3. Cross-cutting rules (apply to all three tables)


| Concern                 | Rule                                                                                                                                                                                                     | Rationale                                                                          |
| ----------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| Primary key             | `external_id` = source-provided stable id, **prefix preserved** (e.g. `in_1Abc…`, `cus_Abc…`). Composite uniqueness: `(_source_system, _source_record_id, _company_id)`.                                 | Round-trip to source; merge-safe across tenants.                                   |
| Timestamps              | ISO 8601 **UTC with `Z`**, no offsets, no naive datetimes. Unknown → empty string (CSV) / `null` (JSON).                                                                                                 | Single timezone convention per merge.dev.                                          |
| Money                   | Decimal **string** in **major units** (dollars, not cents). **Exactly 4 decimal places** (`1250.0000`). Never `float`. Unknown → empty string (CSV) / `null` (JSON).                                     | Avoids Stripe cents bug; preserves precision in CSV; deterministic across mappers. |
| Exchange rate           | Decimal **string**, unitless ratio (not "major units"). Precision not fixed; mapper preserves source precision.                                                                                          | `exchange_rate` is a multiplier, not money.                                        |
| Currency                | ISO-4217, uppercase 3-letter (`USD`, `EUR`). Enforced by regex `^[A-Z]{3}$`.                                                                                                                             | Matches merge.dev.                                                                 |
| Enums                   | Exact merge.dev values, UPPER_SNAKE_CASE. Unknown source values → row reject (not silent `null`).                                                                                                        | Prevents status drift.                                                             |
| Booleans                | `true` / `false` lowercase in CSV; real `bool` in JSON.                                                                                                                                                  | RFC 4180-safe.                                                                     |
| Nullable arrays         | Serialized as **minified JSON strings** in CSV cells (`addresses`, `email_addresses`, `phone_numbers`). Keys alphabetically sorted; absent sub-fields are omitted, never `null`.                         | Keeps the mid-layer flat-CSV while round-tripping merge.dev nested objects.        |
| Unmapped source columns | Preserved in `_unmapped` as a minified JSON object with alphabetically sorted keys. Use `{}` or empty string when there is nothing to preserve — both are legal. **Goal: no source data loss** (PRD §3). | `_unmapped` is nullable; the column is always present in the header.               |
| `remote_was_deleted`    | `false` default. `true` means the source tombstoned the record; the row is still emitted so deletes propagate.                                                                                           | Append-only delta semantics.                                                       |


---

## 4. Table: `invoices` (merge.dev Accounting Invoice)

**Reference:** [https://docs.merge.dev/merge-unified/accounting/common-models/invoices/list](https://docs.merge.dev/merge-unified/accounting/common-models/invoices/list)
**Schema:** `schemas/midlayer/v1/invoice.schema.json`
**Pydantic model:** `schemas.midlayer.v1.models.Invoice`

### Business meaning

One row = one invoice (receivable) or bill (payable). The `type` enum distinguishes the two, matching merge.dev.

### Fields


| Column                         | Type           | Nullable             | merge.dev field             | Notes                                                                                  |
| ------------------------------ | -------------- | -------------------- | --------------------------- | -------------------------------------------------------------------------------------- |
| `external_id`                  | string         | **no**               | `remote_id` / raw source id | Preserve source prefix (`in_1Abc…`).                                                   |
| `type`                         | enum           | yes                  | `type`                      | `ACCOUNTS_RECEIVABLE` | `ACCOUNTS_PAYABLE`.                                            |
| `number`                       | string         | yes                  | `number`                    | Human invoice number (`INV-0001`).                                                     |
| `contact_external_id`          | string         | yes                  | `contact` (FK)              | FK → `customers.external_id`.                                                          |
| `issue_date`                   | datetime       | yes                  | `issue_date`                | ISO 8601 UTC.                                                                          |
| `due_date`                     | datetime       | yes                  | `due_date`                  |                                                                                        |
| `paid_on_date`                 | datetime       | yes                  | `paid_on_date`              |                                                                                        |
| `memo`                         | string         | yes                  | `memo`                      | Free text / description.                                                               |
| `currency`                     | string         | yes                  | `currency`                  | ISO-4217 upper.                                                                        |
| `exchange_rate`                | decimal string | yes                  | `exchange_rate`             |                                                                                        |
| `total_discount`               | decimal string | yes                  | `total_discount`            | Major units.                                                                           |
| `sub_total`                    | decimal string | yes                  | `sub_total`                 | Major units.                                                                           |
| `total_tax_amount`             | decimal string | yes                  | `total_tax_amount`          | Major units.                                                                           |
| `total_amount`                 | decimal string | yes                  | `total_amount`              | Major units.                                                                           |
| `balance`                      | decimal string | yes                  | `balance`                   | Outstanding amount.                                                                    |
| `status`                       | enum           | yes                  | `status`                    | `DRAFT` | `OPEN` | `PAID` | `UNCOLLECTIBLE` | `VOID` | `PARTIALLY_PAID` | `SUBMITTED`. |
| `remote_was_deleted`           | bool           | no (default `false`) | `remote_was_deleted`        |                                                                                        |
| `_unmapped`                    | JSON string    | yes                  |                             | Source-specific columns preserved here.                                                |
| `_source_system` … `_row_hash` | metadata       | **no**               |                             | See §3.                                                                                |


### Merge.dev fields deliberately **not** modeled at v1

`company`, `payments`, `tracking_categories`, `line_items`, `applied_payments`, `applied_credit_notes`, `inclusive_of_tax`, `accounting_period`. These belong to the transformed `target_`* layer or to a future `invoice_line_items` table. Any source values for these get preserved under `_unmapped`.

### Source mapping notes

- **Stripe** `amount_`* fields are integers in cents → divide by 100 and format as decimal string.
- **Stripe** `created`, `due_date`, `finalized_at` are Unix timestamps → convert to ISO 8601 UTC.
- Stripe status mapping: `draft→DRAFT`, `open→OPEN`, `paid→PAID`, `uncollectible→UNCOLLECTIBLE`, `void→VOID`. `finalized` (ambiguous) → row **reject** unless a per-mapping override is configured.

---

## 5. Table: `customers` (merge.dev Accounting Contact)

**Reference:** [https://docs.merge.dev/merge-unified/accounting/common-models/contacts/list](https://docs.merge.dev/merge-unified/accounting/common-models/contacts/list)
**Schema:** `schemas/midlayer/v1/customer.schema.json`
**Pydantic model:** `schemas.midlayer.v1.models.Customer`

### Business meaning

One row = one billable entity. Classified by `is_customer` / `is_supplier` (both may be true for firms acting as both), per merge.dev's Accounting Contact.

### Fields


| Column                | Type           | Nullable             | merge.dev field      | Notes                                                         |
| --------------------- | -------------- | -------------------- | -------------------- | ------------------------------------------------------------- |
| `external_id`         | string         | **no**               | `remote_id`          | Preserve prefix (`cus_Abc…`).                                 |
| `name`                | string         | yes                  | `name`               | Legal or display name.                                        |
| `is_supplier`         | bool           | no (default `false`) | `is_supplier`        |                                                               |
| `is_customer`         | bool           | no (default `true`)  | `is_customer`        | Default aligns with MVP AR focus.                             |
| `email_address`       | string (email) | yes                  | `email_address`      | Singular — matches merge.dev Accounting Contact (not CRM).    |
| `tax_number`          | string         | yes                  | `tax_number`         | VAT/EIN etc.                                                  |
| `status`              | enum           | yes                  | `status`             | `ACTIVE` | `ARCHIVED`.                                        |
| `currency`            | string         | yes                  | `currency`           | Default billing currency (ISO-4217).                          |
| `remote_updated_at`   | datetime       | yes                  | `remote_updated_at`  |                                                               |
| `phone_number`        | string         | yes                  | `phone_number`       | Singular (one canonical). Freeform string; do not pre-format. |
| `addresses`           | JSON string    | yes                  | `addresses`          | Minified JSON array of merge.dev Address objects.             |
| `remote_was_deleted`  | bool           | no (default `false`) | `remote_was_deleted` |                                                               |
| `_unmapped`, metadata | …              | …                    | …                    | See §3.                                                       |


### Merge.dev fields deliberately **not** modeled at v1

`company`, `addresses[].country/state` sub-detail beyond the freeform string (nested inside the JSON cell but not promoted to columns), `payment_terms`, `channel`. Preserved under `_unmapped` when encountered.

### Address JSON shape

Follow merge.dev's `Address` common sub-model. Minified, keys alphabetized:

```json
[{"address_type":"BILLING","city":"San Francisco","country":"US","full_address":"123 Market St, San Francisco, CA","state":"CA","street_1":"123 Market St","zip_code":"94103"}]
```

The mapper is allowed to populate only the subset it has; absent keys are omitted (not `null`).

---

## 6. Table: `contacts` (merge.dev CRM Contact)

**Reference:** [https://docs.merge.dev/merge-unified/crm/common-models/contacts/list](https://docs.merge.dev/merge-unified/crm/common-models/contacts/list)
**Schema:** `schemas/midlayer/v1/contact.schema.json`
**Pydantic model:** `schemas.midlayer.v1.models.Contact`

### Business meaning

One row = one person in a CRM-style relationship (sales/BD). Linked to an account (company) via `account_external_id`; distinct from the billable entities in `customers`.

### Fields


| Column                | Type        | Nullable             | merge.dev field      | Notes                                                                   |
| --------------------- | ----------- | -------------------- | -------------------- | ----------------------------------------------------------------------- |
| `external_id`         | string      | **no**               | `remote_id`          | For Google Sheets seeds, email is a reasonable stable id.               |
| `first_name`          | string      | yes                  | `first_name`         |                                                                         |
| `last_name`           | string      | yes                  | `last_name`          |                                                                         |
| `account_external_id` | string      | yes                  | `account` (FK)       | FK → an Account common model (out of MVP) or the source's company name. |
| `addresses`           | JSON string | yes                  | `addresses`          | Array of merge.dev Address objects.                                     |
| `email_addresses`     | JSON string | yes                  | `email_addresses`    | Array of `{email_address, email_address_type}`.                         |
| `phone_numbers`       | JSON string | yes                  | `phone_numbers`      | Array of `{phone_number, phone_number_type}`.                           |
| `last_activity_at`    | datetime    | yes                  | `last_activity_at`   | Most recent sales-touch timestamp.                                      |
| `remote_created_at`   | datetime    | yes                  | `remote_created_at`  |                                                                         |
| `remote_was_deleted`  | bool        | no (default `false`) | `remote_was_deleted` |                                                                         |
| `_unmapped`, metadata | …           | …                    | …                    | See §3.                                                                 |


### Why plurals here (vs. singular in `customers`)

That is merge.dev's convention: CRM Contact models people with potentially many channels (multiple personal + work emails/phones), while Accounting Contact models a billable entity where a single canonical email/phone is the norm. We mirror it exactly.

### Nested-array JSON shapes

```json
// email_addresses
[{"email_address":"alice@acme.example","email_address_type":"WORK"}]

// phone_numbers
[{"phone_number":"+1 (415) 555-0101","phone_number_type":"WORK"}]

// addresses (same Address object as §5)
[{"address_type":"PRIMARY","full_address":"123 Market St, San Francisco, CA"}]
```

Enums used inside these cells (`email_address_type`, `phone_number_type`, `address_type`) follow merge.dev's enums: `PERSONAL`, `WORK`, `PRIMARY`, `BILLING`, `SHIPPING`, `OTHER`.

---

## 7. Metadata block (identical across all three tables)


| Column              | Type                   | Example                                      | Meaning                                                                  |
| ------------------- | ---------------------- | -------------------------------------------- | ------------------------------------------------------------------------ |
| `_source_system`    | string                 | `stripe`                                     | Slug of the ingesting connector.                                         |
| `_source_record_id` | string                 | `in_1Abc001`                                 | Raw source id, before normalization.                                     |
| `_company_id`       | string                 | `acme-co`                                    | Internal tenant id.                                                      |
| `_ingested_at`      | datetime               | `2026-04-18T08:00:00Z`                       | ISO 8601 UTC; stamped once per run.                                      |
| `_source_file`      | string                 | `seeds/stripe/acme-co/invoices/sample_1.csv` | Repo-relative path (or connector-job URI).                               |
| `_mapping_version`  | string                 | `stripe.invoice@0.1.0`                       | Semver of the mapping artifact used.                                     |
| `_row_hash`         | string                 | `a1b2…` (SHA-256 hex, 64 chars, lowercase)   | SHA-256 of the canonicalized row (see §7.1); drives delta dedupe.        |
| `_unmapped`         | JSON string (nullable) | `{"description":"EU billing"}`               | Source columns the mapper could not map; `{}` or empty string when none. |


### 7.1 `_row_hash` canonicalization (exact recipe)

Every mapper MUST compute `_row_hash` the same way, or delta dedupe breaks. Given a row's **mapped public fields** (everything between `external_id` and `remote_was_deleted` inclusive, per the table's column list), build a canonical representation:

1. **Scope:** mapped public fields only. **Exclude** `_unmapped` and all metadata (`_source_`*, `_company_id`, `_ingested_at`, `_mapping_version`, `_row_hash`). This keeps the hash stable against mapping-artifact bumps and against preserved-but-unmodeled source columns.
2. **Build a dict** keyed by mid-layer column name. Values:
  - `null` / unknown → omit the key entirely (do **not** emit `"field": null`).
  - String → the exact CSV cell string (after any trim/normalization the mapper performs).
  - Decimal → the same 4-decimal string used in the CSV (`"1250.0000"`).
  - Datetime → ISO 8601 UTC `Z` string.
  - Boolean → JSON `true` / `false`.
  - JSON-array columns (`addresses`, `email_addresses`, `phone_numbers`) → parse the minified JSON; include as the parsed array with keys alphabetically sorted inside each object.
3. **Serialize** via `json.dumps(d, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`.
4. **Hash:** `sha256(serialized.encode("utf-8")).hexdigest()` — 64 lowercase hex chars.

Two rows with the same mapped content produce the same `_row_hash` regardless of source system, ingestion time, or unmapped columns.

## 8. Versioning & change control

- Schemas are frozen under `schemas/midlayer/v1/`. Additive nullable fields may stay on `v1` **with a `_mapping_version` bump**.
- Any rename, type change, or removal requires a new folder `schemas/midlayer/v2/` and a dual-write period.
- Each row carries `_mapping_version`; `_manifest/<date>.json` carries `schema_version`. Consumers pin both.

## 9. How this guide fits into the pipeline

```
                                  ┌──────────────────────────┐
 raw source rows  ──► mapper ──►  │   mid-layer v1 row       │  ──► loader ──► Supabase Postgres
 (Stripe CSV,                     │ (this schema guide)      │         │
  Google Sheets, …)               └──────────────────────────┘         │
                                                                        ▼
                                              midlayer-schema-guide/midlayer-db-spec.md
                                              (how the row lands in `mid_*` / `target_*`)
```

- **This document (`midlayer-schema-guide/midlayer-schema-guide.md`)** defines *what* a mid-layer row is (semantics, types, enums, merge.dev alignment).
- **`midlayer-schema-guide/midlayer-db-spec.md`** defines *how* those rows are stored in Supabase Postgres (`mid_*`, `target_*`, load metadata, validation gate).
- **`mira/supabase/load_mid_from_mapper.py`** is the current repo entrypoint that runs the generated mapper and loads the resulting mid-layer rows into `mid_*`.
- **`seeds/samples/midlayer-csv/`** is a historical fixture set from the earlier CSV-first contract and remains useful as sample normalized records.

### Precedence when these disagree

1. The JSON Schemas (`midlayer-schema-guide/midlayer/v1/*.schema.json`) are the machine-checkable contract for **which fields exist, their types, nullability, and enum values**.
2. This guide is authoritative for **semantics, formatting conventions, and merge.dev alignment** (e.g. money in major units with 4 decimal places, ISO 8601 UTC with `Z`, alphabetical key ordering in JSON cells). Where a convention is not expressible in JSON Schema, this guide wins and the mapper must enforce it.
3. `midlayer-db-spec.md` is authoritative for **relational storage concerns**: table families, load metadata, validation gate, and initial-vs-delta semantics.
4. `schemas.midlayer.v1.models.{INVOICE,CUSTOMER,CONTACT}_COLUMNS` is authoritative for **CSV header order**. Markdown tables in this guide are illustrative; if they drift, trust the Python list.

## 10. Confirmation checklist

- `midlayer-schema-guide/midlayer/v1/invoice.schema.json` exists and is aligned with merge.dev Accounting Invoice.
- `midlayer-schema-guide/midlayer/v1/customer.schema.json` exists and is aligned with merge.dev Accounting Contact.
- `midlayer-schema-guide/midlayer/v1/contact.schema.json` exists and is aligned with merge.dev CRM Contact.
- All three schemas share the same metadata block and enforce `additionalProperties: false`.
- Pydantic models in `midlayer-schema-guide/midlayer/v1/models.py` mirror the JSON Schemas and define canonical column order.
- Database storage contract documented separately in `midlayer-schema-guide/midlayer-db-spec.md`.
- Historical worked examples for all three tables committed under `seeds/samples/midlayer-csv/`.
