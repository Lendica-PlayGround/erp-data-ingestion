"""
Main run loop for the Invoiced raw-dump feeder.

Every tick (default 30s) the feeder simulates one "pull" from Invoiced.com:

1. Occasionally onboard a new customer + their primary contact (INSERT).
2. Occasionally add a secondary contact to an existing customer (INSERT).
3. Occasionally mutate an existing customer (terms / credit hold / AutoPay).
4. Always create a handful of fresh invoices for existing customers (INSERT).
5. Progress a random sample of non-terminal invoices through their
   lifecycle (draft → sent → viewed → paid | past_due | voided) (UPDATE).

Everything written to the sheet matches the raw Invoiced.com shape defined
in ``docs/sources/invoiced-data-format.md``. Nested objects (line items,
payment_source, ship_to, metadata) are serialised as JSON into the
``*_json`` columns so downstream mappers can round-trip them losslessly.
"""

from __future__ import annotations

import logging
import random
import signal
import time
from dataclasses import dataclass, field
from typing import Any

import gspread

from .factories import (
    ContactFactory,
    CustomerFactory,
    IdAllocator,
    InvoiceFactory,
)
from .lifecycle import (
    maybe_progress_invoice,
    maybe_update_contact,
    maybe_update_customer,
)
from .schemas import (
    CONTACT_HEADERS,
    CUSTOMER_HEADERS,
    DEFAULT_WORKSHEETS,
    INVOICE_HEADERS,
    TERMINAL_INVOICE_STATUSES,
)
from .sheets import (
    append_records,
    load_credentials,
    open_or_create_worksheet,
    rewrite_row,
)


log = logging.getLogger(__name__)

_SHUTDOWN = False


def _handle_sigterm(signum, frame):  # noqa: ARG001
    global _SHUTDOWN
    _SHUTDOWN = True
    log.info("Received signal %s — finishing current tick then exiting.", signum)


# ---------------------------------------------------------------------------
# In-memory state rehydrated from existing sheet contents
# ---------------------------------------------------------------------------

@dataclass
class InvoiceRef:
    """Minimal mutable view of an invoice we've written or observed."""

    record: dict
    row: int  # 1-based sheet row

    @property
    def status(self) -> str:
        return str(self.record.get("status", ""))


@dataclass
class FeederState:
    customers: dict[int, dict] = field(default_factory=dict)   # id → record (trimmed)
    contacts_by_customer: dict[int, list[int]] = field(default_factory=dict)
    invoices: dict[int, InvoiceRef] = field(default_factory=dict)

    def customer_ids(self) -> list[int]:
        return list(self.customers.keys())


def _rehydrate(
    customers_ws: gspread.Worksheet,
    contacts_ws: gspread.Worksheet,
    invoices_ws: gspread.Worksheet,
) -> FeederState:
    """Best-effort: read enough of each worksheet to keep IDs monotonic and
    know which invoices are still in-flight."""
    state = FeederState()

    # Customers: only keep a lightweight projection (enough to mint invoices).
    cust_rows = customers_ws.get_all_records() or []
    for r in cust_rows:
        try:
            cid = int(r.get("id") or 0)
        except (TypeError, ValueError):
            continue
        if cid <= 0:
            continue
        state.customers[cid] = {
            "id": cid,
            "name": r.get("name"),
            "email": r.get("email"),
            "currency": r.get("currency") or "usd",
            "autopay": str(r.get("autopay")).lower() == "true",
            "payment_terms": r.get("payment_terms") or "NET 30",
            "taxable": str(r.get("taxable")).lower() == "true",
            "credit_hold": str(r.get("credit_hold")).lower() == "true",
            "address1": r.get("address1"),
            "city": r.get("city"),
            "state": r.get("state"),
            "postal_code": r.get("postal_code"),
            "country": r.get("country"),
        }

    # Contacts: just index FKs for quick lookup.
    contact_rows = contacts_ws.get_all_records() or []
    for r in contact_rows:
        try:
            cust_fk = int(r.get("customer") or 0)
        except (TypeError, ValueError):
            continue
        if cust_fk <= 0:
            continue
        state.contacts_by_customer.setdefault(cust_fk, []).append(
            int(r.get("id") or 0)
        )

    # Invoices: full record (so we can mutate + rewrite) keyed by id, plus row #.
    inv_rows = invoices_ws.get_all_records() or []
    for idx, r in enumerate(inv_rows, start=2):  # +2: skip header, 1-based rows
        try:
            iid = int(r.get("id") or 0)
        except (TypeError, ValueError):
            continue
        if iid <= 0:
            continue
        record = _inflate_invoice_row(r)
        state.invoices[iid] = InvoiceRef(record=record, row=idx)

    return state


def _inflate_invoice_row(row: dict) -> dict:
    """Convert a flattened invoice row back into the nested Invoiced shape,
    enough for lifecycle transitions and re-serialization."""
    import json as _json

    def _parse_bool(v: Any) -> bool:
        return str(v).lower() == "true"

    def _parse_json(v: Any) -> Any:
        if v in (None, ""):
            return None
        if isinstance(v, (dict, list)):
            return v
        try:
            return _json.loads(v)
        except (ValueError, TypeError):
            return None

    def _opt_int(v: Any) -> int | None:
        if v in (None, ""):
            return None
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    def _opt_float(v: Any) -> float | None:
        if v in (None, ""):
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    return {
        "id": _opt_int(row.get("id")),
        "object": row.get("object") or "invoice",
        "customer": _opt_int(row.get("customer")),
        "name": row.get("name") or None,
        "number": row.get("number"),
        "autopay": _parse_bool(row.get("autopay")),
        "currency": row.get("currency") or "usd",
        "draft": _parse_bool(row.get("draft")),
        "closed": _parse_bool(row.get("closed")),
        "paid": _parse_bool(row.get("paid")),
        "status": row.get("status") or "not_sent",
        "attempt_count": _opt_int(row.get("attempt_count")) or 0,
        "next_payment_attempt": _opt_int(row.get("next_payment_attempt")),
        "subscription": _opt_int(row.get("subscription")),
        "date": _opt_int(row.get("date")) or 0,
        "due_date": _opt_int(row.get("due_date")) or 0,
        "payment_terms": row.get("payment_terms") or "NET 14",
        "purchase_order": row.get("purchase_order") or None,
        "notes": row.get("notes") or None,
        "subtotal": _opt_float(row.get("subtotal")) or 0.0,
        "total": _opt_float(row.get("total")) or 0.0,
        "balance": _opt_float(row.get("balance")) or 0.0,
        "payment_plan": _opt_int(row.get("payment_plan")),
        "url": row.get("url"),
        "payment_url": row.get("payment_url"),
        "pdf_url": row.get("pdf_url"),
        "created_at": _opt_int(row.get("created_at")) or 0,
        "updated_at": _opt_int(row.get("updated_at")) or 0,
        "items": _parse_json(row.get("items_json")) or [],
        "discounts": _parse_json(row.get("discounts_json")) or [],
        "taxes": _parse_json(row.get("taxes_json")) or [],
        "ship_to": _parse_json(row.get("ship_to_json")),
        "metadata": _parse_json(row.get("metadata_json")) or [],
    }


# ---------------------------------------------------------------------------
# Per-tick scenario driver
# ---------------------------------------------------------------------------

@dataclass
class RunConfig:
    spreadsheet_id: str
    worksheet_customers: str
    worksheet_contacts: str
    worksheet_invoices: str
    interval_seconds: int
    invoices_per_tick: int
    new_customer_prob: float
    secondary_contact_prob: float
    customer_mutate_prob: float
    lifecycle_flip_target: int
    seed: int | None
    once: bool


def run(cfg: RunConfig) -> None:
    rng = random.Random(cfg.seed)
    if cfg.seed is not None:
        random.seed(cfg.seed)

    creds = load_credentials()
    client = gspread.authorize(creds)

    ws_cust = open_or_create_worksheet(
        client, cfg.spreadsheet_id, cfg.worksheet_customers, CUSTOMER_HEADERS,
    )
    ws_cont = open_or_create_worksheet(
        client, cfg.spreadsheet_id, cfg.worksheet_contacts, CONTACT_HEADERS,
    )
    ws_inv = open_or_create_worksheet(
        client, cfg.spreadsheet_id, cfg.worksheet_invoices, INVOICE_HEADERS,
    )

    state = _rehydrate(ws_cust, ws_cont, ws_inv)

    # Allocators: bump above any existing IDs so we never collide.
    cust_alloc = IdAllocator(start=10_000)
    cont_alloc = IdAllocator(start=20_000)
    inv_alloc = IdAllocator(start=40_000)
    li_alloc = IdAllocator(start=80_000)
    tax_alloc = IdAllocator(start=90_000)
    for cid in state.customers:
        cust_alloc.bump_floor(cid)
    for ids in state.contacts_by_customer.values():
        for i in ids:
            cont_alloc.bump_floor(i)
    for iid, ref in state.invoices.items():
        inv_alloc.bump_floor(iid)
        for li in ref.record.get("items") or []:
            try:
                li_alloc.bump_floor(int(li.get("id") or 0))
            except (TypeError, ValueError):
                pass

    cust_factory = CustomerFactory(alloc=cust_alloc, rng=rng, starting_number=len(state.customers) + 1)
    cont_factory = ContactFactory(alloc=cont_alloc, rng=rng)
    inv_factory = InvoiceFactory(
        alloc=inv_alloc,
        line_item_alloc=li_alloc,
        tax_alloc=tax_alloc,
        rng=rng,
        starting_number=max(len(state.invoices) + 1, 16),
    )

    # If the sheet is empty, seed it with a couple of customers so invoice
    # creation has something to attach to.
    if not state.customers:
        seeded: list[dict] = []
        for _ in range(3):
            c = cust_factory.make()
            seeded.append(c)
            state.customers[c["id"]] = _trim_customer(c)
            primary_contact = cont_factory.make(c, primary=True)
            state.contacts_by_customer.setdefault(c["id"], []).append(primary_contact["id"])
            append_records(ws_cont, [primary_contact], CONTACT_HEADERS)
        append_records(ws_cust, seeded, CUSTOMER_HEADERS)
        log.info("Bootstrapped empty sheet with %d seed customers.", len(seeded))

    signal.signal(signal.SIGINT, _handle_sigterm)
    signal.signal(signal.SIGTERM, _handle_sigterm)

    tick = 0
    while not _SHUTDOWN:
        tick += 1
        t0 = time.monotonic()
        try:
            stats = _run_one_tick(
                cfg=cfg,
                rng=rng,
                state=state,
                cust_factory=cust_factory,
                cont_factory=cont_factory,
                inv_factory=inv_factory,
                ws_cust=ws_cust,
                ws_cont=ws_cont,
                ws_inv=ws_inv,
            )
            log.info(
                "tick=%d %s elapsed=%.2fs",
                tick,
                " ".join(f"{k}={v}" for k, v in stats.items()),
                time.monotonic() - t0,
            )
        except gspread.exceptions.APIError as exc:
            log.error("Google Sheets API error on tick %d: %s", tick, exc)
        except Exception:  # noqa: BLE001
            log.exception("Unexpected error on tick %d — will retry next interval.", tick)

        if cfg.once or _SHUTDOWN:
            break

        remaining = cfg.interval_seconds
        while remaining > 0 and not _SHUTDOWN:
            time.sleep(min(1, remaining))
            remaining -= 1


def _run_one_tick(
    *,
    cfg: RunConfig,
    rng: random.Random,
    state: FeederState,
    cust_factory: CustomerFactory,
    cont_factory: ContactFactory,
    inv_factory: InvoiceFactory,
    ws_cust: gspread.Worksheet,
    ws_cont: gspread.Worksheet,
    ws_inv: gspread.Worksheet,
) -> dict[str, int]:
    new_customers: list[dict] = []
    new_contacts: list[dict] = []
    new_invoices: list[InvoiceRef] = []

    # 1) New customer onboarding (+ primary contact).
    if rng.random() < cfg.new_customer_prob:
        c = cust_factory.make()
        new_customers.append(c)
        state.customers[c["id"]] = _trim_customer(c)
        primary_contact = cont_factory.make(c, primary=True)
        new_contacts.append(primary_contact)
        state.contacts_by_customer.setdefault(c["id"], []).append(primary_contact["id"])

    # 2) Secondary contact for an existing customer.
    if state.customers and rng.random() < cfg.secondary_contact_prob:
        target_id = rng.choice(list(state.customers.keys()))
        secondary = cont_factory.make(state.customers[target_id], primary=False)
        new_contacts.append(secondary)
        state.contacts_by_customer.setdefault(target_id, []).append(secondary["id"])

    # 3) Mutate an existing customer (rare). Fire a full-row rewrite.
    customer_updates_rewritten = 0
    if state.customers and rng.random() < cfg.customer_mutate_prob:
        target_id = rng.choice(list(state.customers.keys()))
        # We only hold a projection in-memory; to rewrite faithfully we'd
        # need the full row. Fetch it on demand from the sheet.
        row_idx, full_record = _fetch_customer_row(ws_cust, target_id)
        if full_record is not None and maybe_update_customer(full_record, rng):
            rewrite_row(ws_cust, row_idx, full_record, CUSTOMER_HEADERS)
            # Refresh projection so new invoices pick up the new terms etc.
            state.customers[target_id].update({
                "payment_terms": full_record.get("payment_terms"),
                "autopay": bool(full_record.get("autopay")),
                "credit_hold": bool(full_record.get("credit_hold")),
            })
            customer_updates_rewritten = 1

    # 4) Fresh invoices for existing customers (skip credit-held ones).
    eligible = [
        cid for cid, c in state.customers.items()
        if not c.get("credit_hold")
    ]
    if eligible:
        for _ in range(cfg.invoices_per_tick):
            cust_id = rng.choice(eligible)
            inv = inv_factory.make(state.customers[cust_id])
            new_invoices.append(InvoiceRef(record=inv, row=-1))  # row filled on append

    # --- APPEND PHASE ---------------------------------------------------

    if new_customers:
        append_records(ws_cust, new_customers, CUSTOMER_HEADERS)

    if new_contacts:
        append_records(ws_cont, new_contacts, CONTACT_HEADERS)

    appended_invoice_count = 0
    if new_invoices:
        # We need the starting row number *before* we append so we can track
        # row indices for later lifecycle rewrites.
        first_row = _next_empty_row(ws_inv)
        append_records(
            ws_inv,
            [ref.record for ref in new_invoices],
            INVOICE_HEADERS,
        )
        for offset, ref in enumerate(new_invoices):
            ref.row = first_row + offset
            state.invoices[ref.record["id"]] = ref
        appended_invoice_count = len(new_invoices)

    # --- LIFECYCLE PHASE -------------------------------------------------

    flipped = 0
    if state.invoices and cfg.lifecycle_flip_target > 0:
        candidates = [
            ref for ref in state.invoices.values()
            if ref.status not in TERMINAL_INVOICE_STATUSES
        ]
        rng.shuffle(candidates)
        for ref in candidates[: cfg.lifecycle_flip_target]:
            if maybe_progress_invoice(ref.record, rng):
                rewrite_row(ws_inv, ref.row, ref.record, INVOICE_HEADERS)
                flipped += 1

    return {
        "new_customers": len(new_customers),
        "new_contacts": len(new_contacts),
        "new_invoices": appended_invoice_count,
        "customer_updates": customer_updates_rewritten,
        "invoice_lifecycle_flips": flipped,
    }


def _trim_customer(c: dict) -> dict:
    """Keep just the fields needed for invoice minting in the in-memory state."""
    return {
        "id": c["id"],
        "name": c.get("name"),
        "email": c.get("email"),
        "currency": c.get("currency") or "usd",
        "autopay": bool(c.get("autopay")),
        "payment_terms": c.get("payment_terms") or "NET 30",
        "taxable": bool(c.get("taxable", True)),
        "credit_hold": bool(c.get("credit_hold")),
        "address1": c.get("address1"),
        "city": c.get("city"),
        "state": c.get("state"),
        "postal_code": c.get("postal_code"),
        "country": c.get("country"),
    }


def _next_empty_row(ws: gspread.Worksheet) -> int:
    """Return the 1-based row number where the next ``append_rows`` will land.

    ``gspread.Worksheet.append_rows`` writes after the last non-empty row.
    """
    return len(ws.col_values(1)) + 1


def _fetch_customer_row(ws: gspread.Worksheet, customer_id: int) -> tuple[int, dict | None]:
    """Find the sheet row for ``customer_id`` and inflate it into a dict.

    Also re-parses ``*_json`` columns back into nested objects under their
    un-suffixed key so that :func:`rewrite_row` round-trips the record
    cleanly (rewrite_row re-serialises JSON columns from the un-suffixed key).
    """
    import json as _json

    id_col = ws.col_values(CUSTOMER_HEADERS.index("id") + 1)
    # id_col[0] is "id" header; data starts at index 1 / sheet row 2.
    for idx, val in enumerate(id_col[1:], start=2):
        if str(val) == str(customer_id):
            values = ws.row_values(idx)
            record = dict(zip(
                CUSTOMER_HEADERS,
                values + [""] * (len(CUSTOMER_HEADERS) - len(values)),
            ))
            # Coerce the booleans we may flip.
            record["autopay"] = str(record.get("autopay")).lower() == "true"
            record["credit_hold"] = str(record.get("credit_hold")).lower() == "true"
            record["taxable"] = str(record.get("taxable")).lower() == "true"
            record["chase"] = str(record.get("chase")).lower() == "true"
            try:
                record["id"] = int(record.get("id") or 0)
            except (TypeError, ValueError):
                record["id"] = customer_id
            # Re-hydrate JSON-serialised columns.
            for col in CUSTOMER_HEADERS:
                if col.endswith("_json"):
                    raw_key = col[: -len("_json")]
                    raw_val = record.get(col, "")
                    if raw_val in (None, ""):
                        record[raw_key] = None
                        continue
                    try:
                        record[raw_key] = _json.loads(raw_val)
                    except (ValueError, TypeError):
                        record[raw_key] = None
            return idx, record
    return -1, None


__all__ = ["run", "RunConfig", "DEFAULT_WORKSHEETS"]
