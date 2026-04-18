# Google Sheets seeds — `acme-co`

**Source:** Google Sheets API (`spreadsheets.values.get` on a contacts tab).
**Credentials ref:** `GOOGLE_SHEETS_SA_KEY` — service-account JSON key, stored in `.env` (not checked in).
**Company:** `acme-co`

## Known quirks (called out in `docs/0001-prd.md`)

- **Messy header row** — row 1 is a human-typed banner, row 2 is blank, the
  real header is row 3. The mapping agent must detect header row automatically.
- **Extra unmapped columns** — e.g. `Notes` — preserved under `_unmapped` JSON.
- **Non-ASCII names and addresses** — `Müller`, `Café`, etc. (UTF-8 required).
- **Free-form phone numbers** — `+1 (415) 555-0101`, `4155550123`,
  `+33 1 23 45 67 89`. Kept as-is in `phone_numbers`.
- **`Last Touch`** is sometimes `not-a-date` — rows with unparseable timestamps
  go to `_rejects/`.

## Files

| File | Rows | Purpose |
| :--- | :--- | :--- |
| `contacts/sample_1.csv` | 3 | Clean fixture with 2-row banner before the header. |
| `contacts/sample_dirty.csv` | 3 | Missing last name, missing email + non-ASCII, bad date in `Last Touch`, extra `Notes` column. |
