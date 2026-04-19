"""
Invoice state-machine transitions.

Mirrors the statuses documented at https://developer.invoiced.com/api/invoices
(`draft, not_sent, sent, viewed, past_due, pending, paid, voided`) and the
informal progression described in ``docs/sources/invoiced-data-format.md``.

Each transition function returns the (possibly mutated) invoice dict AND a
flag indicating whether anything actually changed, so callers can skip
pointless sheet writes.
"""

from __future__ import annotations

import random
from datetime import datetime, timezone

from .schemas import TERMINAL_INVOICE_STATUSES


def _now_ts() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def maybe_progress_invoice(invoice: dict, rng: random.Random) -> bool:
    """Attempt a single lifecycle transition on ``invoice`` in-place.

    Returns True if the invoice was mutated (caller should re-write the row).
    """
    status = invoice.get("status")
    if status in TERMINAL_INVOICE_STATUSES or invoice.get("closed"):
        return False

    now = _now_ts()
    due_date = int(invoice.get("due_date") or 0)

    # Forced transition: past-due if due_date has elapsed and status is open.
    if status in ("sent", "viewed") and due_date and now > due_date:
        invoice["status"] = "past_due"
        invoice["updated_at"] = now
        return True

    # Probabilistic progression per status.
    roll = rng.random()

    if status == "draft":
        if roll < 0.6:
            invoice["status"] = "not_sent"
            invoice["draft"] = False
            invoice["updated_at"] = now
            return True
        return False

    if status == "not_sent":
        if roll < 0.7:
            invoice["status"] = "sent"
            invoice["updated_at"] = now
            return True
        return False

    if status == "sent":
        if roll < 0.45:
            invoice["status"] = "viewed"
            invoice["updated_at"] = now
            return True
        if roll < 0.60:  # 0.45..0.60 => direct pay (e.g. portal)
            _mark_paid(invoice, now)
            return True
        if roll < 0.63:
            _mark_voided(invoice, now)
            return True
        return False

    if status == "viewed":
        if roll < 0.55:
            _mark_paid(invoice, now)
            return True
        if roll < 0.58:
            _mark_voided(invoice, now)
            return True
        return False

    if status == "past_due":
        if roll < 0.50:
            _mark_paid(invoice, now)
            return True
        if roll < 0.55:
            _mark_voided(invoice, now)
            return True
        return False

    # Unknown / transient status: leave untouched.
    return False


def _mark_paid(invoice: dict, now: int) -> None:
    invoice["status"] = "paid"
    invoice["paid"] = True
    invoice["balance"] = 0.0
    invoice["attempt_count"] = int(invoice.get("attempt_count") or 0) + 1
    invoice["updated_at"] = now


def _mark_voided(invoice: dict, now: int) -> None:
    invoice["status"] = "voided"
    invoice["closed"] = True
    invoice["updated_at"] = now


def maybe_update_customer(customer: dict, rng: random.Random) -> bool:
    """Small chance of mutating a customer (credit hold toggle, terms change)."""
    now = _now_ts()
    roll = rng.random()
    if roll < 0.35:
        # Flip credit_hold.
        customer["credit_hold"] = not bool(customer.get("credit_hold"))
        customer["updated_at"] = now
        return True
    if roll < 0.55:
        # Change payment terms.
        alternatives = ["NET 7", "NET 14", "NET 30", "NET 60"]
        current = customer.get("payment_terms")
        choices = [t for t in alternatives if t != current] or alternatives
        customer["payment_terms"] = rng.choice(choices)
        customer["updated_at"] = now
        return True
    if roll < 0.70:
        # Toggle autopay.
        customer["autopay"] = not bool(customer.get("autopay"))
        customer["updated_at"] = now
        return True
    return False


def maybe_update_contact(contact: dict, rng: random.Random) -> bool:
    """Small chance of mutating a contact (email change, sms flip)."""
    now = _now_ts()
    roll = rng.random()
    if roll < 0.5:
        # Email change: replace the local part with something new.
        email = contact.get("email") or ""
        if "@" in email:
            _, domain = email.split("@", 1)
            new_local = "".join(rng.choices("abcdefghijklmnopqrstuvwxyz", k=6))
            contact["email"] = f"{new_local}@{domain}"
            contact["updated_at"] = now
            return True
    if roll < 0.85:
        contact["sms_enabled"] = not bool(contact.get("sms_enabled"))
        contact["updated_at"] = now
        return True
    return False


__all__ = [
    "maybe_progress_invoice",
    "maybe_update_customer",
    "maybe_update_contact",
]
