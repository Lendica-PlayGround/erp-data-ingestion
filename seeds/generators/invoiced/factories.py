"""
Factories that mint Invoiced-shaped dicts (Customer / Contact / Invoice).

Every field in each returned dict is taken directly from
https://developer.invoiced.com/. No invented fields. Monetary amounts use
major units (floats rounded to 2 dp) to match the Invoiced API.

These factories are pure / deterministic when seeded with a Random instance.
"""

from __future__ import annotations

import random
import string
from datetime import datetime, timedelta, timezone
from typing import Iterable


# ---------------------------------------------------------------------------
# Business domain — "Div's Furniture Manufacturing Co" style catalog.
# Kept parallel to gsheets_invoice_feeder.py so both feeders share flavor.
# ---------------------------------------------------------------------------

_COMPANY_PREFIXES: list[str] = [
    "Hometown", "Urban Loft", "Maple & Oak", "Nordic Nest", "Castillo",
    "Riverbend", "Blueprint", "Sunset Staging", "Harbor Office", "Fernwood",
    "Cobalt", "Silver Birch", "Granite", "Lakeshore", "Copper Hill",
    "Ironwood", "Evergreen", "Meridian", "Coastal", "Westgate",
]
_COMPANY_SUFFIXES: list[str] = [
    "Interiors", "Retail", "Design Studio", "Hospitality Group", "Hotels",
    "Architects", "LLC", "Solutions", "Coworking", "Trading Co.",
    "Holdings", "Partners", "Group", "Co.", "Industries",
]

_FIRST_NAMES: list[str] = [
    "Avery", "Bailey", "Casey", "Dakota", "Emerson", "Finley", "Gray",
    "Harper", "Indigo", "Jordan", "Kennedy", "Logan", "Morgan", "Noa",
    "Oakley", "Parker", "Quinn", "Reese", "Sage", "Tatum",
]
_LAST_NAMES: list[str] = [
    "Alvarez", "Brooks", "Chen", "Delgado", "Edwards", "Fischer", "Gupta",
    "Hansen", "Ibarra", "Johansson", "Kaur", "Liu", "Martinez", "Nakamura",
    "Okafor", "Patel", "Rossi", "Silva", "Tanaka", "Underwood",
]

_US_CITIES: list[tuple[str, str, str]] = [
    # (city, state, postal_code)
    ("Austin", "TX", "78701"),
    ("Portland", "OR", "97205"),
    ("Asheville", "NC", "28801"),
    ("Madison", "WI", "53703"),
    ("Boulder", "CO", "80302"),
    ("Burlington", "VT", "05401"),
    ("Savannah", "GA", "31401"),
    ("Providence", "RI", "02903"),
    ("Santa Fe", "NM", "87501"),
    ("Missoula", "MT", "59801"),
]

_PRODUCT_CATALOG: list[tuple[str, str, float]] = [
    # (name, type, unit_cost in major units)
    ("Walnut dining table (seats 8)",      "product", 2450.00),
    ("Oak office desk, 72in",              "product",  895.00),
    ("Lounge armchair, tufted",            "product",  649.00),
    ("Modular sectional sofa",             "product", 3200.00),
    ("Bookshelf, 5-shelf ash",             "product",  420.00),
    ("Conference table, 12ft maple",       "product", 4100.00),
    ("Ergonomic task chair",               "product",  375.00),
    ("Hotel bed frame, queen",             "product",  520.00),
    ("Reception desk, custom",             "product", 5800.00),
    ("Café bar stool",                     "product",  145.00),
    ("Upholstery refinishing, lobby",      "service", 1850.00),
    ("Custom millwork, storefront",        "service", 7200.00),
    ("White-glove delivery",               "service",  295.00),
    ("On-site assembly",                   "service",  180.00),
]

_PAYMENT_TERMS: list[str] = ["NET 7", "NET 14", "NET 30", "NET 60", "AutoPay"]
_CURRENCIES: list[str] = ["usd", "usd", "usd", "usd", "eur", "cad"]
_PORTAL = "divsfurniture.invoiced.com"


def _now() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def _jitter_seconds(rng: random.Random, low: int, high: int) -> int:
    return rng.randint(low, high)


def _slug(rng: random.Random, n: int = 24) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(rng.choices(alphabet, k=n))


# ---------------------------------------------------------------------------
# ID allocators
# ---------------------------------------------------------------------------

class IdAllocator:
    """Monotonic integer ID allocator (thread-unsafe; the feeder is single-threaded)."""

    def __init__(self, start: int = 1) -> None:
        self._next = max(1, int(start))

    def bump_floor(self, floor: int) -> None:
        self._next = max(self._next, int(floor) + 1)

    def next(self) -> int:
        n = self._next
        self._next += 1
        return n

    @property
    def peek(self) -> int:
        return self._next


# ---------------------------------------------------------------------------
# Customer factory
# ---------------------------------------------------------------------------

class CustomerFactory:
    def __init__(
        self,
        *,
        alloc: IdAllocator,
        rng: random.Random,
        starting_number: int = 1,
    ) -> None:
        self._alloc = alloc
        self._rng = rng
        self._number_counter = max(1, starting_number)

    def bump_number_floor(self, floor: int) -> None:
        self._number_counter = max(self._number_counter, int(floor) + 1)

    def make(self) -> dict:
        cust_id = self._alloc.next()
        number = f"CUST-{self._number_counter:04d}"
        self._number_counter += 1

        prefix = self._rng.choice(_COMPANY_PREFIXES)
        suffix = self._rng.choice(_COMPANY_SUFFIXES)
        name = f"{prefix} {suffix}"
        is_company = self._rng.random() < 0.9

        slug = "".join(
            ch for ch in name.lower().replace("&", "and") if ch.isalnum()
        )[:18] or "customer"
        email_domain = f"{slug}.example"
        email = f"ap@{email_domain}"

        city, state, postal = self._rng.choice(_US_CITIES)
        autopay = self._rng.random() < 0.35
        terms = self._rng.choice(_PAYMENT_TERMS) if not autopay else "AutoPay"
        currency = self._rng.choice(_CURRENCIES)

        created = _now() - _jitter_seconds(self._rng, 0, 60 * 60 * 24 * 30)

        return {
            "id": cust_id,
            "object": "customer",
            "number": number,
            "name": name,
            "email": email,
            "type": "company" if is_company else "person",
            "autopay": autopay,
            "autopay_delay_days": None,
            "payment_terms": terms,
            "attention_to": None,
            "address1": f"{self._rng.randint(10, 9999)} {self._rng.choice(['Main', 'Oak', 'Market', 'Elm', '2nd', 'Pine'])} St",
            "address2": None,
            "city": city,
            "state": state,
            "postal_code": postal,
            "country": "US",
            "language": "en",
            "currency": currency,
            "phone": f"+1-555-{self._rng.randint(100, 999)}-{self._rng.randint(1000, 9999)}",
            "chase": True,
            "chasing_cadence": None,
            "next_chase_step": None,
            "credit_hold": False,
            "credit_limit": None,
            "owner": None,
            "taxable": True,
            "tax_id": None,
            "avalara_entity_use_code": None,
            "avalara_exemption_number": None,
            "parent_customer": None,
            "notes": None,
            "sign_up_page": None,
            "sign_up_url": None,
            "statement_pdf_url": f"https://{_PORTAL}/statements/{_slug(self._rng)}/pdf",
            "ach_gateway": None,
            "cc_gateway": None,
            "created_at": created,
            "updated_at": created,
            "payment_source": None,
            "taxes": [],
            "metadata": {"account_rep": self._rng.choice(_FIRST_NAMES)},
        }


# ---------------------------------------------------------------------------
# Contact factory
# ---------------------------------------------------------------------------

class ContactFactory:
    def __init__(self, *, alloc: IdAllocator, rng: random.Random) -> None:
        self._alloc = alloc
        self._rng = rng

    def _person(self) -> tuple[str, str]:
        first = self._rng.choice(_FIRST_NAMES)
        last = self._rng.choice(_LAST_NAMES)
        return first, last

    def make(self, customer: dict, *, primary: bool) -> dict:
        first, last = self._person()
        name = f"{first} {last}"
        email_user = f"{first}.{last}".lower()
        email_domain = customer["email"].split("@", 1)[1]
        created = _now()

        titles_primary = ["Accounts Payable", "Finance Manager", "Owner", "Office Manager"]
        titles_secondary = ["Purchasing", "Operations", "Logistics Coordinator", "Receiving"]
        title = self._rng.choice(titles_primary if primary else titles_secondary)

        return {
            "customer": customer["id"],
            "id": self._alloc.next(),
            "object": "contact",
            "name": name,
            "title": title,
            "email": f"{email_user}@{email_domain}",
            "phone": f"+1-555-{self._rng.randint(100, 999)}-{self._rng.randint(1000, 9999)}",
            "primary": primary,
            "sms_enabled": self._rng.random() < 0.25 if not primary else False,
            "department": "Finance" if primary else self._rng.choice(["Ops", "Procurement", "Warehouse"]),
            "address1": customer.get("address1"),
            "address2": None,
            "city": customer.get("city"),
            "state": customer.get("state"),
            "postal_code": customer.get("postal_code"),
            "country": customer.get("country"),
            "created_at": created,
            "updated_at": created,
        }


# ---------------------------------------------------------------------------
# Invoice factory
# ---------------------------------------------------------------------------

class InvoiceFactory:
    def __init__(
        self,
        *,
        alloc: IdAllocator,
        line_item_alloc: IdAllocator,
        tax_alloc: IdAllocator,
        rng: random.Random,
        starting_number: int = 16,
    ) -> None:
        self._alloc = alloc
        self._li_alloc = line_item_alloc
        self._tax_alloc = tax_alloc
        self._rng = rng
        self._number_counter = max(1, starting_number)

    def bump_number_floor(self, floor: int) -> None:
        self._number_counter = max(self._number_counter, int(floor) + 1)

    def _make_line_items(self) -> list[dict]:
        n = self._rng.choices([1, 2, 3, 4], weights=[2, 4, 3, 1])[0]
        items: list[dict] = []
        for _ in range(n):
            name, kind, base_cost = self._rng.choice(_PRODUCT_CATALOG)
            qty = self._rng.choices([1, 2, 3, 5, 10, 20], weights=[5, 4, 3, 2, 2, 1])[0]
            unit_cost = round(base_cost * self._rng.uniform(0.9, 1.1), 2)
            items.append({
                "id": self._li_alloc.next(),
                "object": "line_item",
                "catalog_item": None,
                "type": kind,
                "name": name,
                "description": None,
                "quantity": qty,
                "unit_cost": unit_cost,
                "amount": round(qty * unit_cost, 2),
                "discountable": True,
                "discounts": [],
                "taxable": True,
                "taxes": [],
                "metadata": [],
            })
        return items

    def make(self, customer: dict) -> dict:
        inv_id = self._alloc.next()
        number = f"INV-{self._number_counter:04d}"
        self._number_counter += 1

        items = self._make_line_items()
        subtotal = round(sum(i["amount"] for i in items), 2)

        taxable = bool(customer.get("taxable", True))
        tax_rate = 0.07 if taxable else 0.0
        tax_amount = round(subtotal * tax_rate, 2)
        taxes: list[dict] = []
        if tax_amount > 0:
            taxes.append({
                "id": self._tax_alloc.next(),
                "object": "tax",
                "amount": tax_amount,
                "tax_rate": None,
            })
        total = round(subtotal + tax_amount, 2)

        autopay = bool(customer.get("autopay", False))
        payment_terms = customer.get("payment_terms") or "NET 30"

        created = _now()
        # Invoice date in the last 3 days; due date from terms.
        date = created - _jitter_seconds(self._rng, 0, 60 * 60 * 24 * 3)
        term_days = {
            "NET 7": 7, "NET 14": 14, "NET 30": 30, "NET 60": 60, "AutoPay": 0,
        }.get(payment_terms, 14)
        due_date = date + term_days * 86400 if term_days else date

        # Most new invoices start as not_sent; some are draft; a few autopay-paid.
        if autopay and self._rng.random() < 0.35:
            status, draft, paid, balance = "paid", False, True, 0.0
        elif self._rng.random() < 0.15:
            status, draft, paid, balance = "draft", True, False, total
        else:
            status, draft, paid, balance = "not_sent", False, False, total

        slug = _slug(self._rng)
        url = f"https://{_PORTAL}/invoices/{slug}"

        return {
            "id": inv_id,
            "object": "invoice",
            "customer": customer["id"],
            "name": None,
            "number": number,
            "autopay": autopay,
            "currency": customer.get("currency") or "usd",
            "draft": draft,
            "closed": False,
            "paid": paid,
            "status": status,
            "attempt_count": 1 if paid and autopay else 0,
            "next_payment_attempt": None,
            "subscription": None,
            "date": date,
            "due_date": due_date,
            "payment_terms": payment_terms,
            "purchase_order": None,
            "notes": None,
            "subtotal": subtotal,
            "total": total,
            "balance": balance,
            "payment_plan": None,
            "url": url,
            "payment_url": f"{url}/payment",
            "pdf_url": f"{url}/pdf",
            "created_at": created,
            "updated_at": created,
            "items": items,
            "discounts": [],
            "taxes": taxes,
            "ship_to": None,
            "metadata": [],
        }


__all__ = [
    "IdAllocator",
    "CustomerFactory",
    "ContactFactory",
    "InvoiceFactory",
]
