"""
Google Sheets invoice feeder.

Continuously appends synthetic invoices to a target Google Sheet and, on each
tick, flips a small random subset of previously-OPEN invoices to PAID so
downstream delta ingestion has both INSERTs and UPDATEs to chew on.

The generated columns intentionally mirror the Stripe invoice shape used by
``seeds/stripe/acme-co/invoices/sample_1.csv`` so the existing Stripe mapper
(``tools/mapper/stripe.py``) can be pointed at the exported sheet with zero
extra wiring:

    id, number, customer, customer_email, currency, amount_due, amount_paid,
    amount_remaining, status, created, due_date, finalized_at, description

Auth:
  - Prefers ``GOOGLE_SHEETS_SA_KEY`` (inline JSON) when present.
  - Otherwise falls back to ``GOOGLE_APPLICATION_CREDENTIALS`` (file path).

Usage:
    # Defaults read from .env (GSHEETS_FEEDER_*).
    python -m tools.generators.gsheets_invoice_feeder

    # One-shot (append a single batch and exit) — useful in CI / smoke tests.
    python -m tools.generators.gsheets_invoice_feeder --once

    # Explicit overrides.
    python -m tools.generators.gsheets_invoice_feeder \
        --spreadsheet-id 1Ap858t1QMAnKaGNMq7_tIMhahORKohjxvTu5H2GhkUI \
        --worksheet invoices \
        --interval 60 \
        --batch-size 5
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import signal
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Sequence

try:
    import gspread
    from google.oauth2.service_account import Credentials
except ImportError as exc:  # pragma: no cover - import-time guard
    raise SystemExit(
        "Missing dependency: "
        f"{exc.name}. Install with `pip install -r requirements.txt`."
    ) from exc


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

HEADERS: list[str] = [
    "id",
    "number",
    "customer",
    "customer_email",
    "currency",
    "amount_due",
    "amount_paid",
    "amount_remaining",
    "status",
    "created",
    "due_date",
    "finalized_at",
    "description",
]

# Domain flavor: "Div's Furniture Manufacturing Co".
CUSTOMERS: list[tuple[str, str, str]] = [
    # (customer_id, display_name, email)
    ("cus_HOME001", "Hometown Interiors",        "ap@hometown-interiors.example"),
    ("cus_URBN002", "Urban Loft Co.",            "billing@urbanloft.example"),
    ("cus_MAPL003", "Maple & Oak Design Studio", "finance@mapleoak.example"),
    ("cus_NORD004", "Nordic Nest Retail",        "invoices@nordicnest.example"),
    ("cus_CAST005", "Castillo Hospitality Group","ap@castillohospitality.example"),
    ("cus_RVRB006", "Riverbend Hotels",          "payables@riverbendhotels.example"),
    ("cus_BLUE007", "Blueprint Architects",      "ops@blueprint-arch.example"),
    ("cus_SUNS008", "Sunset Staging LLC",        "accounts@sunsetstaging.example"),
    ("cus_HRBR009", "Harbor Office Solutions",   "ap@harboroffice.example"),
    ("cus_FERN010", "Fernwood Coworking",        "billing@fernwood.example"),
]

PRODUCT_LINES: list[str] = [
    "Walnut dining table (seats 8)",
    "Oak office desk, 72in",
    "Lounge armchair, tufted",
    "Modular sectional sofa",
    "Bookshelf, 5-shelf ash",
    "Conference table, 12ft maple",
    "Ergonomic task chair batch (x10)",
    "Hotel bed frame, queen (x20)",
    "Reception desk, custom",
    "Café bar stools (x24)",
    "Upholstery refinishing — lobby",
    "Custom millwork — storefront",
]

CURRENCIES: list[str] = ["USD", "USD", "USD", "USD", "EUR", "CAD"]  # weighted

# Lifecycle of newly-minted invoices (weighted). Stripe-style lowercase values.
NEW_STATUS_POOL: list[str] = [
    "open", "open", "open", "open",  # most are OPEN
    "paid",
    "draft",
]


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Invoice:
    id: str
    number: str
    customer: str
    customer_email: str
    currency: str
    amount_due: int       # cents, Stripe-style
    amount_paid: int
    amount_remaining: int
    status: str
    created: int          # unix seconds
    due_date: int
    finalized_at: int
    description: str

    def as_row(self) -> list[str]:
        return [
            self.id,
            self.number,
            self.customer,
            self.customer_email,
            self.currency,
            str(self.amount_due),
            str(self.amount_paid),
            str(self.amount_remaining),
            self.status,
            str(self.created),
            str(self.due_date),
            str(self.finalized_at),
            self.description,
        ]


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------

class InvoiceFactory:
    """Stateless-ish factory: owns the monotonically increasing invoice number."""

    def __init__(self, *, starting_number: int = 1, rng: random.Random | None = None) -> None:
        self._counter = starting_number
        self._rng = rng or random.Random()

    def set_starting_number(self, n: int) -> None:
        self._counter = max(self._counter, n)

    def make(self) -> Invoice:
        n = self._counter
        self._counter += 1

        cust_id, cust_name, cust_email = self._rng.choice(CUSTOMERS)
        currency = self._rng.choice(CURRENCIES)
        description = self._rng.choice(PRODUCT_LINES)

        # Amounts in cents, 250.00 – 18 500.00 in major units.
        amount_due = self._rng.randint(25_000, 1_850_000)
        status = self._rng.choice(NEW_STATUS_POOL)

        if status == "paid":
            amount_paid = amount_due
            amount_remaining = 0
        elif status == "draft":
            amount_paid = 0
            amount_remaining = amount_due
        else:
            amount_paid = 0
            amount_remaining = amount_due

        now = datetime.now(timezone.utc)
        # Created within the last 3 days, due 14 days out.
        created_dt = now - timedelta(hours=self._rng.randint(0, 72))
        due_dt = created_dt + timedelta(days=self._rng.choice([7, 14, 14, 30]))

        # Stripe-ish id: in_1<random suffix>, 24 chars total.
        suffix = "".join(self._rng.choices("ABCDEFGHJKLMNPQRSTUVWXYZ23456789", k=21))
        inv_id = f"in_1{suffix}"

        return Invoice(
            id=inv_id,
            number=f"INV-{n:05d}",
            customer=cust_id,
            customer_email=cust_email,
            currency=currency,
            amount_due=amount_due,
            amount_paid=amount_paid,
            amount_remaining=amount_remaining,
            status=status,
            created=int(created_dt.timestamp()),
            due_date=int(due_dt.timestamp()),
            finalized_at=int(created_dt.timestamp()),
            description=f"{description} — {cust_name}",
        )


# ---------------------------------------------------------------------------
# Sheet I/O
# ---------------------------------------------------------------------------

def _load_credentials() -> Credentials:
    """Resolve service-account creds from env. Inline JSON takes precedence."""
    inline = os.environ.get("GOOGLE_SHEETS_SA_KEY", "").strip()
    if inline:
        try:
            info = json.loads(inline)
        except json.JSONDecodeError as exc:
            raise SystemExit(
                "GOOGLE_SHEETS_SA_KEY is set but is not valid JSON. "
                "Paste the full service-account key as a single-line JSON string, "
                "or unset it and use GOOGLE_APPLICATION_CREDENTIALS instead."
            ) from exc
        return Credentials.from_service_account_info(info, scopes=SCOPES)

    path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    if path:
        p = Path(path).expanduser()
        if not p.is_file():
            raise SystemExit(
                f"GOOGLE_APPLICATION_CREDENTIALS={path!r} does not point to a file."
            )
        return Credentials.from_service_account_file(str(p), scopes=SCOPES)

    raise SystemExit(
        "No Google credentials found. Set GOOGLE_SHEETS_SA_KEY (inline JSON) "
        "or GOOGLE_APPLICATION_CREDENTIALS (path). See .env.example."
    )


def _open_worksheet(client: gspread.Client, spreadsheet_id: str, worksheet: str) -> gspread.Worksheet:
    sh = client.open_by_key(spreadsheet_id)
    try:
        ws = sh.worksheet(worksheet)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=worksheet, rows=2000, cols=max(26, len(HEADERS)))
        ws.update("A1", [HEADERS], value_input_option="RAW")
        return ws

    # Ensure the header row matches; seed it if the sheet is empty.
    first_row = ws.row_values(1)
    if not first_row:
        ws.update("A1", [HEADERS], value_input_option="RAW")
    elif first_row[: len(HEADERS)] != HEADERS:
        logging.warning(
            "Worksheet %r header does not match generator schema; appending rows anyway. "
            "Existing header: %s",
            worksheet, first_row,
        )
    return ws


def _max_invoice_number(ws: gspread.Worksheet) -> int:
    """Scan column B (`number`) for the largest INV-##### value."""
    try:
        col = ws.col_values(HEADERS.index("number") + 1)
    except Exception:  # pragma: no cover - network flakes
        return 0
    highest = 0
    for v in col[1:]:  # skip header
        if isinstance(v, str) and v.startswith("INV-"):
            try:
                highest = max(highest, int(v.split("-", 1)[1]))
            except ValueError:
                continue
    return highest


def _find_open_invoice_rows(ws: gspread.Worksheet, limit: int) -> list[int]:
    """Return 1-based row indices whose `status` column is currently 'open'."""
    status_col = ws.col_values(HEADERS.index("status") + 1)
    rows: list[int] = []
    # status_col[0] is the header.
    for idx, value in enumerate(status_col[1:], start=2):
        if value == "open":
            rows.append(idx)
    if len(rows) <= limit:
        return rows
    return random.sample(rows, limit)


def _mark_rows_paid(ws: gspread.Worksheet, row_indices: Sequence[int]) -> None:
    """Batch-update selected rows: set status=paid, move balance to amount_paid."""
    if not row_indices:
        return

    updates = []
    for r in row_indices:
        # We already know amount_due is in column F (index 6). Read the row to
        # get the authoritative current value rather than trusting a cached copy.
        row_values = ws.row_values(r)
        try:
            amount_due = row_values[HEADERS.index("amount_due")]
        except IndexError:
            amount_due = "0"

        updates.append({"range": f"I{r}", "values": [["paid"]]})           # status
        updates.append({"range": f"G{r}", "values": [[amount_due]]})       # amount_paid
        updates.append({"range": f"H{r}", "values": [["0"]]})              # amount_remaining

    ws.batch_update(updates, value_input_option="RAW")


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

_SHUTDOWN = False


def _handle_sigterm(signum, frame):  # noqa: ARG001
    global _SHUTDOWN
    _SHUTDOWN = True
    logging.info("Received signal %s — finishing current tick then exiting.", signum)


def _append_batch(ws: gspread.Worksheet, invoices: Iterable[Invoice]) -> int:
    rows = [inv.as_row() for inv in invoices]
    if not rows:
        return 0
    ws.append_rows(rows, value_input_option="RAW", insert_data_option="INSERT_ROWS")
    return len(rows)


def run(
    *,
    spreadsheet_id: str,
    worksheet: str,
    interval_seconds: int,
    batch_size: int,
    once: bool,
    paid_flip_ratio: float,
    seed: int | None,
) -> None:
    rng = random.Random(seed)
    # Seed module-level random too (used by _find_open_invoice_rows sampling).
    if seed is not None:
        random.seed(seed)

    creds = _load_credentials()
    client = gspread.authorize(creds)
    ws = _open_worksheet(client, spreadsheet_id, worksheet)

    factory = InvoiceFactory(rng=rng)
    # Pick up where a previous run left off so INV numbers stay monotonic.
    factory.set_starting_number(_max_invoice_number(ws) + 1)
    logging.info(
        "Connected to sheet %s / worksheet %r. Next invoice number: INV-%05d.",
        spreadsheet_id, worksheet, factory._counter,  # noqa: SLF001
    )

    signal.signal(signal.SIGINT, _handle_sigterm)
    signal.signal(signal.SIGTERM, _handle_sigterm)

    tick = 0
    while not _SHUTDOWN:
        tick += 1
        t0 = time.monotonic()
        try:
            new_invoices = [factory.make() for _ in range(batch_size)]
            inserted = _append_batch(ws, new_invoices)

            # Simulate lifecycle updates: flip a fraction of still-open invoices to PAID.
            flip_limit = max(1, int(batch_size * paid_flip_ratio)) if paid_flip_ratio > 0 else 0
            flipped_rows = _find_open_invoice_rows(ws, flip_limit) if flip_limit else []
            if flipped_rows:
                _mark_rows_paid(ws, flipped_rows)

            logging.info(
                "tick=%d appended=%d flipped_to_paid=%d elapsed=%.2fs",
                tick, inserted, len(flipped_rows), time.monotonic() - t0,
            )
        except gspread.exceptions.APIError as exc:
            logging.error("Google Sheets API error on tick %d: %s", tick, exc)
        except Exception:  # noqa: BLE001
            logging.exception("Unexpected error on tick %d — will retry next interval.", tick)

        if once or _SHUTDOWN:
            break

        # Interruptible sleep so SIGINT doesn't have to wait a full minute.
        remaining = interval_seconds
        while remaining > 0 and not _SHUTDOWN:
            time.sleep(min(1, remaining))
            remaining -= 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _load_dotenv(path: Path) -> None:
    """Minimal .env loader so the script works without an extra dependency."""
    if not path.is_file():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python -m tools.generators.gsheets_invoice_feeder",
        description=(
            "Append synthetic invoices to a Google Sheet on a timer. "
            "Defaults come from .env (GSHEETS_FEEDER_*)."
        ),
    )
    p.add_argument(
        "--spreadsheet-id",
        default=os.environ.get("GSHEETS_FEEDER_SPREADSHEET_ID"),
        help="Target Google Sheet ID (from the URL).",
    )
    p.add_argument(
        "--worksheet",
        default=os.environ.get("GSHEETS_FEEDER_WORKSHEET", "invoices"),
        help="Target worksheet/tab name (created if missing). Default: invoices.",
    )
    p.add_argument(
        "--interval",
        type=int,
        default=int(os.environ.get("GSHEETS_FEEDER_INTERVAL_SECONDS", "60")),
        help="Seconds between ticks. Default: 60.",
    )
    p.add_argument(
        "--batch-size",
        type=int,
        default=int(os.environ.get("GSHEETS_FEEDER_BATCH_SIZE", "5")),
        help="Invoices appended per tick. Default: 5.",
    )
    p.add_argument(
        "--paid-flip-ratio",
        type=float,
        default=float(os.environ.get("GSHEETS_FEEDER_PAID_FLIP_RATIO", "0.4")),
        help="Fraction of batch_size used as the upper bound of OPEN→PAID flips per tick.",
    )
    p.add_argument("--once", action="store_true", help="Run a single tick and exit.")
    p.add_argument("--seed", type=int, default=None, help="Seed the RNG for reproducibility.")
    p.add_argument(
        "--log-level",
        default=os.environ.get("LOG_LEVEL", "INFO"),
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    _load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    args = _parse_args(argv if argv is not None else sys.argv[1:])

    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )

    if not args.spreadsheet_id:
        raise SystemExit(
            "No spreadsheet id. Pass --spreadsheet-id or set "
            "GSHEETS_FEEDER_SPREADSHEET_ID in .env."
        )
    if args.batch_size < 1:
        raise SystemExit("--batch-size must be >= 1")
    if args.interval < 1:
        raise SystemExit("--interval must be >= 1")

    run(
        spreadsheet_id=args.spreadsheet_id,
        worksheet=args.worksheet,
        interval_seconds=args.interval,
        batch_size=args.batch_size,
        once=args.once,
        paid_flip_ratio=max(0.0, args.paid_flip_ratio),
        seed=args.seed,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
