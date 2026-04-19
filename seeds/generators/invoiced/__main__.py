"""
CLI entry point for the Invoiced.com raw-dump feeder.

Usage:
    # Defaults read from .env (INVOICED_FEEDER_*).
    python -m seeds.generators.invoiced

    # One-shot batch (useful in CI / smoke tests).
    python -m seeds.generators.invoiced --once

    # Explicit overrides.
    python -m seeds.generators.invoiced \
        --spreadsheet-id 1Ap858t1QMAnKaGNMq7_tIMhahORKohjxvTu5H2GhkUI \
        --interval 30 \
        --invoices-per-tick 3
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from .feeder import RunConfig, run


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader — mirrors gsheets_invoice_feeder.py."""
    if not path.is_file():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _spreadsheet_id_from_env() -> str | None:
    """First non-empty of INVOICED_FEEDER_* then GSHEETS_FEEDER_* (empty .env counts as unset)."""
    for key in ("INVOICED_FEEDER_SPREADSHEET_ID", "GSHEETS_FEEDER_SPREADSHEET_ID"):
        raw = os.environ.get(key)
        if raw and raw.strip():
            return raw.strip()
    return None


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python -m seeds.generators.invoiced",
        description=(
            "Append simulated Invoiced.com-shaped Customers / Contacts / "
            "Invoices to a Google Sheet on a timer. Defaults come from "
            ".env (INVOICED_FEEDER_* and GSHEETS_FEEDER_SPREADSHEET_ID)."
        ),
    )
    p.add_argument(
        "--spreadsheet-id",
        default=_spreadsheet_id_from_env(),
        help="Target Google Sheet ID (from the URL).",
    )
    p.add_argument(
        "--worksheet-customers",
        default=os.environ.get("INVOICED_FEEDER_WORKSHEET_CUSTOMERS", "customers"),
        help="Worksheet/tab name for Customers. Default: customers.",
    )
    p.add_argument(
        "--worksheet-contacts",
        default=os.environ.get("INVOICED_FEEDER_WORKSHEET_CONTACTS", "contacts"),
        help="Worksheet/tab name for Contacts. Default: contacts.",
    )
    p.add_argument(
        "--worksheet-invoices",
        default=os.environ.get("INVOICED_FEEDER_WORKSHEET_INVOICES", "invoices"),
        help="Worksheet/tab name for Invoices. Default: invoices.",
    )
    p.add_argument(
        "--interval",
        type=int,
        default=int(os.environ.get("INVOICED_FEEDER_INTERVAL_SECONDS", "30")),
        help="Seconds between ticks. Default: 30.",
    )
    p.add_argument(
        "--invoices-per-tick",
        type=int,
        default=int(os.environ.get("INVOICED_FEEDER_INVOICES_PER_TICK", "3")),
        help="Invoices minted per tick. Default: 3.",
    )
    p.add_argument(
        "--new-customer-prob",
        type=float,
        default=float(os.environ.get("INVOICED_FEEDER_NEW_CUSTOMER_PROB", "0.25")),
        help="Per-tick probability of onboarding a brand-new customer. Default: 0.25.",
    )
    p.add_argument(
        "--secondary-contact-prob",
        type=float,
        default=float(os.environ.get("INVOICED_FEEDER_SECONDARY_CONTACT_PROB", "0.15")),
        help="Per-tick probability of adding a secondary contact to an existing customer. Default: 0.15.",
    )
    p.add_argument(
        "--customer-mutate-prob",
        type=float,
        default=float(os.environ.get("INVOICED_FEEDER_CUSTOMER_MUTATE_PROB", "0.1")),
        help="Per-tick probability of mutating an existing customer (terms / credit hold). Default: 0.1.",
    )
    p.add_argument(
        "--lifecycle-flip-target",
        type=int,
        default=int(os.environ.get("INVOICED_FEEDER_LIFECYCLE_FLIP_TARGET", "4")),
        help="Max non-terminal invoices evaluated for state transitions per tick. Default: 4.",
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
    _load_dotenv(Path(__file__).resolve().parents[3] / ".env")
    args = _parse_args(argv if argv is not None else sys.argv[1:])

    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )

    if not args.spreadsheet_id:
        raise SystemExit(
            "No spreadsheet id. Pass --spreadsheet-id or set "
            "INVOICED_FEEDER_SPREADSHEET_ID / GSHEETS_FEEDER_SPREADSHEET_ID in .env."
        )
    if args.interval < 1:
        raise SystemExit("--interval must be >= 1")
    if args.invoices_per_tick < 0:
        raise SystemExit("--invoices-per-tick must be >= 0")

    run(RunConfig(
        spreadsheet_id=args.spreadsheet_id,
        worksheet_customers=args.worksheet_customers,
        worksheet_contacts=args.worksheet_contacts,
        worksheet_invoices=args.worksheet_invoices,
        interval_seconds=args.interval,
        invoices_per_tick=args.invoices_per_tick,
        new_customer_prob=max(0.0, min(1.0, args.new_customer_prob)),
        secondary_contact_prob=max(0.0, min(1.0, args.secondary_contact_prob)),
        customer_mutate_prob=max(0.0, min(1.0, args.customer_mutate_prob)),
        lifecycle_flip_target=max(0, args.lifecycle_flip_target),
        seed=args.seed,
        once=args.once,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
