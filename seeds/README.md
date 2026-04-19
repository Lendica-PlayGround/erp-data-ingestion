# Seeds

Static fixtures live under `samples/`; **live-ish test data** is produced by Google Sheet feeders in `generators/`.

## Setup

1. From the repo root: `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
2. Copy `.env.example` → `.env` and fill in at least:
   - **Google:** `GOOGLE_SHEETS_SA_KEY` or `GOOGLE_APPLICATION_CREDENTIALS` (service account JSON), spreadsheet ID (`GSHEETS_FEEDER_SPREADSHEET_ID` and/or `INVOICED_FEEDER_SPREADSHEET_ID`), and enable **Google Sheets API** (and **Drive API** if needed) in that GCP project. Share the target sheet with the service account as **Editor**.
3. Run commands from the **repo root** so `.env` and relative key paths resolve.

## Generators

| Module | What it does |
|--------|----------------|
| `seeds.generators.invoiced` | Simulated Invoiced.com pull: **customers**, **contacts**, **invoices** tabs (see `docs/sources/invoiced-data-format.md`). |
| `seeds.generators.gsheets_invoice_feeder` | Simpler **Stripe-shaped invoice** rows on one worksheet (mapper smoke tests). |

**One-shot (single batch, then exit):**

```bash
python -m seeds.generators.invoiced --once
python -m seeds.generators.gsheets_invoice_feeder --once
```

**Continuous loop** (omit `--once`; interval from `INVOICED_FEEDER_INTERVAL_SECONDS` / `GSHEETS_FEEDER_INTERVAL_SECONDS` in `.env`):

```bash
python -m seeds.generators.invoiced
python -m seeds.generators.gsheets_invoice_feeder
```

Use `--help` on either module for flags (`--spreadsheet-id`, worksheet names, RNG seed, etc.).
