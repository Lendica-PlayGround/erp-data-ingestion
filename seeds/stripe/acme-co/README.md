# Stripe seeds — `acme-co`

**Source:** Stripe API (simulated CSV export of `invoices.list` and `customers.list`).
**Credentials ref:** `STRIPE_API_KEY` (read-only restricted key). Stored in `.env` (not checked in).
**Company:** `acme-co`

## Known quirks (as called out in `docs/0001-prd.md`)

- **Amounts in cents (integer)** — every monetary field must be divided by `100`
  to land in the mid-layer's `DECIMAL(18,4)` major-unit convention.
- **Currency** comes in lowercase (`usd`) — we upper-case it to ISO-4217 (`USD`).
- **Timestamps are Unix epoch seconds** — converted to ISO 8601 UTC (`...Z`).
- **Invoice id has `in_` prefix** — we preserve it in `external_id`.
- **`status` enum** needs remapping (`paid` → `PAID`, `open` → `OPEN`,
  `uncollectible` → `UNCOLLECTIBLE`, `void` → `VOID`, `draft` → `DRAFT`).

## Files

| File | Rows | Purpose |
| :--- | :--- | :--- |
| `invoices/sample_1.csv` | 3 | Clean fixture — all rows should pass validation. |
| `invoices/sample_dirty.csv` | 3 | One extra source column, one row missing `amount_due`, one row with unknown status, non-ASCII characters. |
| `customers/sample_1.csv` | 3 | Clean fixture with mixed currency + one blank phone. |

## Golden outputs

`expected/` holds the hand-curated mid-layer CSV each mapper run must reproduce
byte-for-byte (modulo `_ingested_at` and `_row_hash`, which are time-dependent).
