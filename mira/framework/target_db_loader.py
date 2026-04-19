from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from psycopg import sql
from psycopg.types.json import Jsonb


def _full_name(first_name: str | None, last_name: str | None) -> str | None:
    parts = [part for part in [first_name, last_name] if part]
    return " ".join(parts) or None


def _aging_bucket(days_outstanding: int | None) -> str | None:
    if days_outstanding is None or days_outstanding <= 0:
        return None
    if days_outstanding <= 30:
        return "1_30"
    if days_outstanding <= 60:
        return "31_60"
    if days_outstanding <= 90:
        return "61_90"
    return "90_plus"


def build_target_customer_row(mid_customer: dict[str, Any]) -> dict[str, Any]:
    return {
        "mid_customer_id": mid_customer["id"],
        "load_batch_id": mid_customer.get("load_batch_id"),
        "company_id": mid_customer["_company_id"],
        "source_system": mid_customer["_source_system"],
        "source_record_id": mid_customer["_source_record_id"],
        "customer_external_id": mid_customer["external_id"],
        "customer_company_name": mid_customer.get("name"),
        "description": None,
        "email_address": mid_customer.get("email_address"),
        "phone_number": mid_customer.get("phone_number"),
        "tax_number": mid_customer.get("tax_number"),
        "customer_status": mid_customer.get("status"),
        "currency": mid_customer.get("currency"),
        "is_supplier": mid_customer.get("is_supplier", False),
        "is_customer": mid_customer.get("is_customer", True),
        "addresses": mid_customer.get("addresses"),
        "remote_updated_at": mid_customer.get("remote_updated_at"),
        "remote_was_deleted": mid_customer.get("remote_was_deleted", False),
        "default_payment_terms": None,
        "credit_limit": None,
        "data_source_type": "midlayer",
        "data_source_name": mid_customer["_source_system"],
        "data_sources": [{"type": "midlayer", "record_id": mid_customer["_source_record_id"]}],
        "transform_version": "v1",
        "transform_metadata": {"source": "mid_customers"},
    }


def build_target_contact_row(mid_contact: dict[str, Any], *, target_customer_id: int | None) -> dict[str, Any]:
    return {
        "mid_contact_id": mid_contact["id"],
        "load_batch_id": mid_contact.get("load_batch_id"),
        "target_customer_id": target_customer_id,
        "company_id": mid_contact["_company_id"],
        "source_system": mid_contact["_source_system"],
        "source_record_id": mid_contact["_source_record_id"],
        "contact_external_id": mid_contact["external_id"],
        "account_external_id": mid_contact.get("account_external_id"),
        "first_name": mid_contact.get("first_name"),
        "last_name": mid_contact.get("last_name"),
        "full_name": _full_name(mid_contact.get("first_name"), mid_contact.get("last_name")),
        "addresses": mid_contact.get("addresses"),
        "email_addresses": mid_contact.get("email_addresses"),
        "phone_numbers": mid_contact.get("phone_numbers"),
        "last_activity_at": mid_contact.get("last_activity_at"),
        "remote_created_at": mid_contact.get("remote_created_at"),
        "remote_was_deleted": mid_contact.get("remote_was_deleted", False),
        "data_source_type": "midlayer",
        "data_source_name": mid_contact["_source_system"],
        "data_sources": [{"type": "midlayer", "record_id": mid_contact["_source_record_id"]}],
        "transform_version": "v1",
        "transform_metadata": {"source": "mid_contacts"},
    }


def build_target_invoice_row(
    mid_invoice: dict[str, Any],
    *,
    target_customer_id: int | None,
    today: datetime | None = None,
) -> dict[str, Any]:
    today = today or datetime.now(timezone.utc)
    balance = mid_invoice.get("balance") or Decimal("0")
    total_amount = mid_invoice.get("total_amount") or Decimal("0")
    paid_amount = total_amount - balance
    due_date = mid_invoice.get("due_date")
    days_outstanding = None
    if due_date is not None:
        days_outstanding = max((today.date() - due_date.date()).days, 0)

    return {
        "mid_invoice_id": mid_invoice["id"],
        "load_batch_id": mid_invoice.get("load_batch_id"),
        "target_customer_id": target_customer_id,
        "company_id": mid_invoice["_company_id"],
        "source_system": mid_invoice["_source_system"],
        "source_record_id": mid_invoice["_source_record_id"],
        "invoice_external_id": mid_invoice["external_id"],
        "invoice_number": mid_invoice.get("number"),
        "contact_external_id": mid_invoice.get("contact_external_id"),
        "customer_external_id": mid_invoice.get("contact_external_id"),
        "invoice_type": mid_invoice.get("type"),
        "issue_date": mid_invoice.get("issue_date").date() if mid_invoice.get("issue_date") else None,
        "due_date": due_date.date() if due_date else None,
        "paid_on_date": mid_invoice.get("paid_on_date").date() if mid_invoice.get("paid_on_date") else None,
        "memo": mid_invoice.get("memo"),
        "currency": mid_invoice.get("currency"),
        "exchange_rate": mid_invoice.get("exchange_rate"),
        "total_discount": mid_invoice.get("total_discount"),
        "sub_total": mid_invoice.get("sub_total"),
        "total_tax_amount": mid_invoice.get("total_tax_amount"),
        "total_amount": total_amount,
        "paid_amount": paid_amount,
        "balance": balance,
        "merge_status": "matched" if target_customer_id else "unmatched_customer",
        "status": mid_invoice.get("status"),
        "days_outstanding": days_outstanding,
        "aging_bucket": _aging_bucket(days_outstanding),
        "disposition": None,
        "remote_was_deleted": mid_invoice.get("remote_was_deleted", False),
        "data_source_type": "midlayer",
        "data_source_name": mid_invoice["_source_system"],
        "data_sources": [{"type": "midlayer", "record_id": mid_invoice["_source_record_id"]}],
        "transform_version": "v1",
        "transform_metadata": {"source": "mid_invoices"},
    }


def _upsert_rows(cur, table: str, rows: list[dict[str, Any]], conflict_columns: tuple[str, ...], id_column: str) -> tuple[int, int]:
    if not rows:
        return (0, 0)

    insert_columns = list(rows[0].keys())
    update_columns = [column for column in insert_columns if column not in {id_column, *conflict_columns}]
    query = sql.SQL(
        """
        insert into public.{table} ({columns})
        values ({values})
        on conflict ({conflict_columns})
        do update set {updates}, updated_at = now()
        returning (xmax = 0) as inserted
        """
    ).format(
        table=sql.Identifier(table),
        columns=sql.SQL(", ").join(sql.Identifier(col) for col in insert_columns),
        values=sql.SQL(", ").join(sql.Placeholder(col) for col in insert_columns),
        conflict_columns=sql.SQL(", ").join(sql.Identifier(col) for col in conflict_columns),
        updates=sql.SQL(", ").join(
            sql.SQL("{} = EXCLUDED.{}").format(sql.Identifier(col), sql.Identifier(col))
            for col in update_columns
        ),
    )

    inserted = 0
    updated = 0
    for row in rows:
        params = {
            key: Jsonb(value) if key in {"data_sources", "transform_metadata"} else value
            for key, value in row.items()
        }
        cur.execute(query, params)
        result = cur.fetchone()
        was_inserted = result["inserted"] if isinstance(result, dict) else result[0]
        if was_inserted:
            inserted += 1
        else:
            updated += 1
    return (inserted, updated)


def load_target_customers(cur, *, company_id: str, source_system: str | None = None) -> tuple[int, int]:
    query = """
        select mc.*
        from public.mid_customers mc
        join public.ingestion_load_batches ilb
          on ilb.id = mc.load_batch_id
        where mc._company_id = %(company_id)s
          and ilb.status = 'completed'
    """
    params: dict[str, Any] = {"company_id": company_id}
    if source_system:
        query += " and _source_system = %(source_system)s"
        params["source_system"] = source_system
    cur.execute(query, params)
    rows = [build_target_customer_row(row) for row in cur.fetchall()]
    return _upsert_rows(cur, "target_customers", rows, ("company_id", "source_system", "source_record_id"), "id")


def load_target_contacts(cur, *, company_id: str, source_system: str | None = None) -> tuple[int, int]:
    query = """
        select mc.*, tc.id as target_customer_id
        from public.mid_contacts mc
        join public.ingestion_load_batches ilb
          on ilb.id = mc.load_batch_id
        left join public.target_customers tc
          on tc.company_id = mc._company_id
         and tc.customer_external_id = mc.account_external_id
        where mc._company_id = %(company_id)s
          and ilb.status = 'completed'
    """
    params: dict[str, Any] = {"company_id": company_id}
    if source_system:
        query += " and mc._source_system = %(source_system)s"
        params["source_system"] = source_system
    cur.execute(query, params)
    rows = [build_target_contact_row(row, target_customer_id=row["target_customer_id"]) for row in cur.fetchall()]
    return _upsert_rows(cur, "target_contacts", rows, ("company_id", "source_system", "source_record_id"), "id")


def load_target_invoices(cur, *, company_id: str, source_system: str | None = None) -> tuple[int, int]:
    query = """
        select mi.*, tc.id as target_customer_id
        from public.mid_invoices mi
        join public.ingestion_load_batches ilb
          on ilb.id = mi.load_batch_id
        left join public.target_customers tc
          on tc.company_id = mi._company_id
         and tc.customer_external_id = mi.contact_external_id
        where mi._company_id = %(company_id)s
          and ilb.status = 'completed'
    """
    params: dict[str, Any] = {"company_id": company_id}
    if source_system:
        query += " and mi._source_system = %(source_system)s"
        params["source_system"] = source_system
    cur.execute(query, params)
    rows = [build_target_invoice_row(row, target_customer_id=row["target_customer_id"]) for row in cur.fetchall()]
    return _upsert_rows(cur, "target_invoices", rows, ("company_id", "source_system", "source_record_id"), "id")
