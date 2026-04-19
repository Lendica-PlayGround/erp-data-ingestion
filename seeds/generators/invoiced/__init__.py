"""
Invoiced.com raw-dump feeder.

Simulates a recurring API pull from invoiced.com (Customers / Contacts /
Invoices) and lands the resulting rows into a Google Sheet.

The public contract for the dumped rows is documented in
``docs/sources/invoiced-data-format.md``. Both the shape of each row and
the lifecycle transitions produced by this feeder match the Invoiced API
documented at https://developer.invoiced.com/.

Entry point:
    python -m seeds.generators.invoiced --once
"""

from .schemas import (
    CUSTOMER_HEADERS,
    CONTACT_HEADERS,
    INVOICE_HEADERS,
    TERMINAL_INVOICE_STATUSES,
)

__all__ = [
    "CUSTOMER_HEADERS",
    "CONTACT_HEADERS",
    "INVOICE_HEADERS",
    "TERMINAL_INVOICE_STATUSES",
]
