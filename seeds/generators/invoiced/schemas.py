"""
Column orders for each Invoiced worksheet.

These lists are the source of truth for the sheet layout: the feeder
serialises records in this exact order, and downstream mappers read them
back by column name. JSON-serialised columns use the ``_json`` suffix.

The shapes match ``docs/sources/invoiced-data-format.md`` 1:1.
"""

from __future__ import annotations


CUSTOMER_HEADERS: list[str] = [
    "id",
    "object",
    "number",
    "name",
    "email",
    "type",
    "autopay",
    "autopay_delay_days",
    "payment_terms",
    "attention_to",
    "address1",
    "address2",
    "city",
    "state",
    "postal_code",
    "country",
    "language",
    "currency",
    "phone",
    "chase",
    "chasing_cadence",
    "next_chase_step",
    "credit_hold",
    "credit_limit",
    "owner",
    "taxable",
    "tax_id",
    "avalara_entity_use_code",
    "avalara_exemption_number",
    "parent_customer",
    "notes",
    "sign_up_page",
    "sign_up_url",
    "statement_pdf_url",
    "ach_gateway",
    "cc_gateway",
    "created_at",
    "updated_at",
    "payment_source_json",
    "taxes_json",
    "metadata_json",
]

CONTACT_HEADERS: list[str] = [
    # `customer` is a project-added FK (not part of Invoiced's response).
    "customer",
    "id",
    "object",
    "name",
    "title",
    "email",
    "phone",
    "primary",
    "sms_enabled",
    "department",
    "address1",
    "address2",
    "city",
    "state",
    "postal_code",
    "country",
    "created_at",
    "updated_at",
]

INVOICE_HEADERS: list[str] = [
    "id",
    "object",
    "customer",
    "name",
    "number",
    "autopay",
    "currency",
    "draft",
    "closed",
    "paid",
    "status",
    "attempt_count",
    "next_payment_attempt",
    "subscription",
    "date",
    "due_date",
    "payment_terms",
    "purchase_order",
    "notes",
    "subtotal",
    "total",
    "balance",
    "payment_plan",
    "url",
    "payment_url",
    "pdf_url",
    "created_at",
    "updated_at",
    "items_json",
    "discounts_json",
    "taxes_json",
    "ship_to_json",
    "metadata_json",
]

# Invoice statuses that no longer transition further.
TERMINAL_INVOICE_STATUSES: frozenset[str] = frozenset({"paid", "voided"})

# Default worksheet names (one per entity).
DEFAULT_WORKSHEETS: dict[str, str] = {
    "customers": "customers",
    "contacts": "contacts",
    "invoices": "invoices",
}
