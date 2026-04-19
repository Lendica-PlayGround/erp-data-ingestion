from __future__ import annotations

import argparse
import os
from pathlib import Path

import psycopg

MIRA_ROOT = Path(__file__).resolve().parents[1]


def _load_repo_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def _connection_kwargs() -> dict[str, str]:
    return {
        "host": os.environ["POSTGRES_HOST"],
        "port": os.environ.get("POSTGRES_PORT", "5432"),
        "dbname": os.environ["POSTGRES_DB"],
        "user": os.environ["POSTGRES_USER"],
        "password": os.environ["POSTGRES_PASSWORD"],
        "sslmode": os.environ.get("POSTGRES_SSLMODE", "require"),
        "row_factory": psycopg.rows.dict_row,
    }


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    _load_repo_dotenv(repo_root / ".env")

    from framework.target_db_loader import load_target_contacts, load_target_customers, load_target_invoices

    parser = argparse.ArgumentParser(description="Promote mid_* rows into target_* tables.")
    parser.add_argument("--company-id", required=True, help="Company id to promote.")
    parser.add_argument("--source-system", default=None, help="Optional source system filter.")
    parser.add_argument(
        "--table",
        choices=("customers", "contacts", "invoices", "all"),
        default="all",
        help="Which target table(s) to build.",
    )
    args = parser.parse_args()

    jobs = []
    if args.table in {"customers", "all"}:
        jobs.append(("customers", load_target_customers))
    if args.table in {"contacts", "all"}:
        jobs.append(("contacts", load_target_contacts))
    if args.table in {"invoices", "all"}:
        jobs.append(("invoices", load_target_invoices))

    summaries = []
    with psycopg.connect(**_connection_kwargs()) as conn:
        with conn.cursor() as cur:
            for name, fn in jobs:
                inserted, updated = fn(cur, company_id=args.company_id, source_system=args.source_system)
                summaries.append((name, inserted, updated))
        conn.commit()

    for name, inserted, updated in summaries:
        print(f"{name}: inserted={inserted} updated={updated}")


if __name__ == "__main__":
    main()
