# `seeds/samples/midlayer-csv/` — worked example of the mid-layer bucket

This directory is a **concrete, populated example** of what Phase 1's mapper emits
into the `midlayer-csv` bucket (Supabase Storage in production; local mirror in
dev). It exists to make the two authoritative docs real:

- **Schema:** `mira/midlayer-schema-guide/midlayer-schema-guide.md` (uniform data schema, merge.dev-aligned)
- **CSV contract:** `mira/midlayer-schema-guide/midlayer-csv-spec.md` (folder layout, file naming, sidecars, validation)

## What's here

One tenant (`acme-co`), two runs:

- **Initial run, 2026-04-18** — full historical backfill for all three tables
  (3 invoices from Stripe, 3 customers from Stripe, 3 contacts from a Google Sheet).
- **Delta run, 2026-04-19** — one new Stripe invoice picked up overnight.

```
samples/midlayer-csv/
└── acme-co/
    ├── invoices/
    │   ├── initial/
    │   │   ├── acme-co_invoices_initial_20260418.csv
    │   │   └── acme-co_invoices_initial_20260418.csv.meta.json
    │   └── delta/
    │       └── dt=2026-04-19/
    │           ├── acme-co_invoices_delta_20260419_01HWXK9A2Z8F3Q4B7N5M6P1R2S.csv
    │           └── acme-co_invoices_delta_20260419_01HWXK9A2Z8F3Q4B7N5M6P1R2S.csv.meta.json
    ├── customers/
    │   └── initial/
    │       ├── acme-co_customers_initial_20260418.csv
    │       └── acme-co_customers_initial_20260418.csv.meta.json
    ├── contacts/
    │   └── initial/
    │       ├── acme-co_contacts_initial_20260418.csv
    │       └── acme-co_contacts_initial_20260418.csv.meta.json
    └── _manifest/
        ├── 2026-04-18.json      # signals Phase 3 that the initial run is complete
        └── 2026-04-19.json      # signals Phase 3 that the delta run is complete
```

## What to notice

1. **Header order** matches `midlayer.v1.models.{INVOICE,CUSTOMER,CONTACT}_COLUMNS`
   exactly — never reorder.
2. **Metadata columns populated on every row.** `_ingested_at` is one timestamp
   per run (stamped on every row, not per-row). `_row_hash` is SHA-256 hex of the
   canonicalized mapped row (see schema guide §7.1 for the exact recipe) and is
   the primary delta-dedupe key.
3. **Money in major units, decimal string** (`1250.0000`, not `125000` cents).
   Stripe cents are divided by 100 at the mapper boundary.
4. **Timestamps ISO 8601 UTC with `Z`.** Stripe Unix timestamps are converted.
5. **Currency uppercase ISO-4217** (`USD`, `EUR`) — Stripe lowercases; we
   normalize.
6. **`_unmapped` is a minified JSON object with alphabetically sorted keys.**
   Empty is `{}`, never blank. For `customers`, Stripe's `delinquent` and
   `description` land here because merge.dev's Accounting Contact has no direct
   equivalent. For `contacts` (Google Sheets) every column is mapped, so
   `_unmapped` is `{}`.
7. **Nested JSON cells (`addresses`, `email_addresses`, `phone_numbers`)** in
   the `contacts` table are minified JSON arrays of merge.dev sub-objects.
   In CSV, outer quoting uses `"`, inner quotes are doubled per RFC 4180.
8. **Delta file is partitioned under `dt=YYYY-MM-DD/`** and named with the
   Airflow/ULID `run_id`; the initial file has no `run_id` suffix by design
   (there is exactly one per onboarding).
9. **Sidecar `*.csv.meta.json`** accompanies every CSV with `row_count`,
   `reject_count`, `sha256`, `mapping_version`, etc.
10. **`_manifest/<date>.json`** is the Phase-3 trigger. It's emitted only after
    the validation gate passes for all tables in that run.

## Regenerating

These files are hand-curated fixtures — checksums and `_row_hash` values are
illustrative, not computed. The real mapper (Phase 3) will regenerate this
exact layout with real hashes during a run.
