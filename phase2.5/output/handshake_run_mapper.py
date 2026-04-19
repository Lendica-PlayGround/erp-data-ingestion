#!/usr/bin/env python3
"""
Generated mid-layer mapper from Phase 2.5 handshake artifact.

Multi-table mapper for: contacts, customers, invoices.

Implements:
- CLI: --input, --output, --table (contacts|customers|invoices)
- Reads Phase 2 CSV, writes mid-layer `<table>_mapped.csv`
- Applies handshake-defined mappings and processing steps.
"""

import argparse
import csv
import json
import sys
from pathlib import Path
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import re

# ---------------- Handshake-derived configuration ---------------- #

HANDSHAKE_TABLES = {
    "contacts": {
        "phase2_table": "contacts",
        "midlayer_table": "contacts",
        "columns": [
            {"phase2_column": "customer", "midlayer_columns": ["account_external_id"]},
            {"phase2_column": "id", "midlayer_columns": ["external_id"]},
            {"phase2_column": "object", "midlayer_columns": ["other"]},
            {"phase2_column": "name", "midlayer_columns": ["other"]},
            {"phase2_column": "title", "midlayer_columns": ["other"]},
            {"phase2_column": "email", "midlayer_columns": ["email_addresses"]},
            {"phase2_column": "phone", "midlayer_columns": ["phone_numbers"]},
            {"phase2_column": "primary", "midlayer_columns": ["other"]},
            {"phase2_column": "sms_enabled", "midlayer_columns": ["other"]},
            {"phase2_column": "department", "midlayer_columns": ["other"]},
            {"phase2_column": "address1", "midlayer_columns": ["addresses"]},
            {"phase2_column": "address2", "midlayer_columns": ["addresses"]},
            {"phase2_column": "city", "midlayer_columns": ["addresses"]},
            {"phase2_column": "state", "midlayer_columns": ["addresses"]},
            {"phase2_column": "postal_code", "midlayer_columns": ["addresses"]},
            {"phase2_column": "country", "midlayer_columns": ["addresses"]},
            {"phase2_column": "created_at", "midlayer_columns": ["remote_created_at"]},
            {"phase2_column": "updated_at", "midlayer_columns": ["last_activity_at"]},
        ],
    },
    "customers": {
        "phase2_table": "customers",
        "midlayer_table": "customers",
        "columns": [
            {"phase2_column": "id", "midlayer_columns": ["external_id"]},
            {"phase2_column": "object", "midlayer_columns": ["other"]},
            {"phase2_column": "number", "midlayer_columns": ["other"]},
            {"phase2_column": "name", "midlayer_columns": ["name"]},
            {"phase2_column": "email", "midlayer_columns": ["email_address"]},
            {"phase2_column": "type", "midlayer_columns": ["other"]},
            {"phase2_column": "autopay", "midlayer_columns": ["other"]},
            {"phase2_column": "autopay_delay_days", "midlayer_columns": ["other"]},
            {"phase2_column": "payment_terms", "midlayer_columns": ["other"]},
            {"phase2_column": "attention_to", "midlayer_columns": ["other"]},
            {"phase2_column": "address1", "midlayer_columns": ["addresses"]},
            {"phase2_column": "address2", "midlayer_columns": ["addresses"]},
            {"phase2_column": "city", "midlayer_columns": ["addresses"]},
            {"phase2_column": "state", "midlayer_columns": ["addresses"]},
            {"phase2_column": "postal_code", "midlayer_columns": ["addresses"]},
            {"phase2_column": "country", "midlayer_columns": ["addresses", "currency"]},
            {"phase2_column": "language", "midlayer_columns": ["other"]},
            {"phase2_column": "currency", "midlayer_columns": ["currency"]},
            {"phase2_column": "phone", "midlayer_columns": ["phone_number"]},
            {"phase2_column": "chase", "midlayer_columns": ["other"]},
            {"phase2_column": "chasing_cadence", "midlayer_columns": ["other"]},
            {"phase2_column": "next_chase_step", "midlayer_columns": ["other"]},
            {"phase2_column": "credit_hold", "midlayer_columns": ["other"]},
            {"phase2_column": "credit_limit", "midlayer_columns": ["other"]},
            {"phase2_column": "owner", "midlayer_columns": ["other"]},
            {"phase2_column": "taxable", "midlayer_columns": ["other"]},
            {"phase2_column": "tax_id", "midlayer_columns": ["tax_number"]},
            {"phase2_column": "avalara_entity_use_code", "midlayer_columns": ["other"]},
            {"phase2_column": "avalara_exemption_number", "midlayer_columns": ["other"]},
            {"phase2_column": "parent_customer", "midlayer_columns": ["other"]},
            {"phase2_column": "notes", "midlayer_columns": ["other"]},
            {"phase2_column": "sign_up_page", "midlayer_columns": ["other"]},
            {"phase2_column": "sign_up_url", "midlayer_columns": ["other"]},
            {"phase2_column": "statement_pdf_url", "midlayer_columns": ["other"]},
            {"phase2_column": "ach_gateway", "midlayer_columns": ["other"]},
            {"phase2_column": "cc_gateway", "midlayer_columns": ["other"]},
            {"phase2_column": "created_at", "midlayer_columns": ["other"]},
            {"phase2_column": "updated_at", "midlayer_columns": ["other"]},
            {"phase2_column": "payment_source_json", "midlayer_columns": ["other"]},
            {"phase2_column": "taxes_json", "midlayer_columns": ["other"]},
            {"phase2_column": "metadata_json", "midlayer_columns": ["other"]},
        ],
    },
    "invoices": {
        "phase2_table": "invoices",
        "midlayer_table": "invoices",
        "columns": [
            {"phase2_column": "id", "midlayer_columns": ["external_id"]},
            {"phase2_column": "object", "midlayer_columns": ["other"]},
            {"phase2_column": "customer", "midlayer_columns": ["contact_external_id"]},
            {"phase2_column": "name", "midlayer_columns": ["memo"]},
            {"phase2_column": "number", "midlayer_columns": ["number"]},
            {"phase2_column": "autopay", "midlayer_columns": ["other"]},
            {"phase2_column": "currency", "midlayer_columns": ["currency"]},
            {"phase2_column": "draft", "midlayer_columns": ["status"]},
            {"phase2_column": "closed", "midlayer_columns": ["other"]},
            {"phase2_column": "paid", "midlayer_columns": ["paid_on_date", "status"]},
            {"phase2_column": "status", "midlayer_columns": ["status"]},
            {"phase2_column": "attempt_count", "midlayer_columns": ["other"]},
            {"phase2_column": "next_payment_attempt", "midlayer_columns": ["other"]},
            {"phase2_column": "subscription", "midlayer_columns": ["other"]},
            {"phase2_column": "date", "midlayer_columns": ["issue_date"]},
            {"phase2_column": "due_date", "midlayer_columns": ["due_date"]},
            {"phase2_column": "payment_terms", "midlayer_columns": ["other"]},
            {"phase2_column": "purchase_order", "midlayer_columns": ["other"]},
            {"phase2_column": "notes", "midlayer_columns": ["memo"]},
            {"phase2_column": "subtotal", "midlayer_columns": ["sub_total"]},
            {"phase2_column": "total", "midlayer_columns": ["total_amount"]},
            {"phase2_column": "balance", "midlayer_columns": ["balance"]},
            {"phase2_column": "payment_plan", "midlayer_columns": ["other"]},
            {"phase2_column": "url", "midlayer_columns": ["other"]},
            {"phase2_column": "payment_url", "midlayer_columns": ["other"]},
            {"phase2_column": "pdf_url", "midlayer_columns": ["other"]},
            # truncated columns in artifact are treated as "other" if present in source
        ],
    },
}

MID_LAYER_COLUMNS_ORDER = {
    "invoices": [
        "external_id",
        "type",
        "number",
        "contact_external_id",
        "issue_date",
        "due_date",
        "paid_on_date",
        "memo",
        "currency",
        "exchange_rate",
        "total_discount",
        "sub_total",
        "total_tax_amount",
        "total_amount",
        "balance",
        "status",
        "remote_was_deleted",
        "_unmapped",
        "_source_system",
        "_source_record_id",
        "_company_id",
        "_ingested_at",
        "_source_file",
        "_mapping_version",
        "_row_hash",
    ],
    "customers": [
        "external_id",
        "name",
        "is_supplier",
        "is_customer",
        "email_address",
        "tax_number",
        "status",
        "currency",
        "remote_updated_at",
        "phone_number",
        "addresses",
        "remote_was_deleted",
        "_unmapped",
        "_source_system",
        "_source_record_id",
        "_company_id",
        "_ingested_at",
        "_source_file",
        "_mapping_version",
        "_row_hash",
    ],
    "contacts": [
        "external_id",
        "first_name",
        "last_name",
        "account_external_id",
        "addresses",
        "email_addresses",
        "phone_numbers",
        "last_activity_at",
        "remote_created_at",
        "remote_was_deleted",
        "_unmapped",
        "_source_system",
        "_source_record_id",
        "_company_id",
        "_ingested_at",
        "_source_file",
        "_mapping_version",
        "_row_hash",
    ],
}

EMAIL_REGEX = re.compile(r"^[\w\.-]+@[\w\.-]+\.[\w\.-]+$")
CURRENCY_REGEX = re.compile(r"^[A-Z]{3}$")


# ---------------- Utility functions ---------------- #

def to_bool(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    if s in ("true", "t", "1", "yes", "y"):
        return True
    if s in ("false", "f", "0", "no", "n"):
        return False
    return None


def format_bool(value):
    if value is None:
        return ""
    return "true" if value else "false"


def money_to_str(value):
    if value is None or str(value).strip() == "":
        return ""
    try:
        d = Decimal(str(value))
    except InvalidOperation:
        return ""
    return f"{d.quantize(Decimal('0.0001'))}"


def unix_to_iso(value):
    if value is None:
        return ""
    s = str(value).strip()
    if not s:
        return ""
    try:
        iv = int(float(s))
    except ValueError:
        return ""
    dt = datetime.fromtimestamp(iv, tz=timezone.utc)
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_datetime_to_utc_iso(value):
    if value is None:
        return ""
    s = str(value).strip()
    if not s:
        return ""
    # Try common formats; assume UTC if no tz
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%m/%d/%Y %H:%M", "%m/%d/%Y"):
        try:
            dt = datetime.strptime(s, fmt)
            dt = dt.replace(tzinfo=timezone.utc)
            return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")
        except ValueError:
            continue
    # Fallback: try fromisoformat
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    except Exception:
        return ""


def json_dumps_sorted(obj):
    return json.dumps(obj, separators=(",", ":"), sort_keys=True)


def compute_row_hash(row_dict, columns_order):
    # Hash over the CSV cell strings in canonical column order
    hasher = hashlib.sha256()
    for col in columns_order:
        val = row_dict.get(col, "")
        if val is None:
            val = ""
        hasher.update(str(val).encode("utf-8"))
        hasher.update(b"|")
    return hasher.hexdigest()


# ---------------- Row mappers ---------------- #

def map_contacts_row(src, source_system, company_id, ingested_at, source_file, mapping_version):
    out = {col: "" for col in MID_LAYER_COLUMNS_ORDER["contacts"]}
    unmapped = {}

    # external_id
    val = src.get("id", "")
    val = str(val).strip() if val not in (None, "") else ""
    out["external_id"] = val

    # account_external_id from customer
    cust = src.get("customer", "")
    cust = str(cust).strip() if cust not in (None, "") else ""
    out["account_external_id"] = cust

    # email_addresses
    email = src.get("email", "")
    email = str(email).strip()
    if email:
        # basic regex; even if invalid, still store
        entry = {"email_address": email, "email_address_type": "PRIMARY"}
        out["email_addresses"] = json_dumps_sorted([entry])
    else:
        out["email_addresses"] = ""

    # phone_numbers
    phone = src.get("phone", "")
    phone = str(phone).strip()
    if phone:
        entry = {"phone_number": phone, "phone_number_type": "PRIMARY"}
        out["phone_numbers"] = json_dumps_sorted([entry])
    else:
        out["phone_numbers"] = ""

    # addresses (single composed address)
    addr1 = str(src.get("address1", "") or "").strip()
    addr2 = str(src.get("address2", "") or "").strip()
    city = str(src.get("city", "") or "").strip()
    state = str(src.get("state", "") or "").strip()
    postal_code = str(src.get("postal_code", "") or "").strip()
    country = str(src.get("country", "") or "").strip().upper()
    addr_obj = {}
    if addr1:
        addr_obj["street_1"] = addr1
    if addr2:
        addr_obj["street_2"] = addr2
    if city:
        addr_obj["city"] = city
    if state:
        addr_obj["state"] = state
    if postal_code:
        addr_obj["postal_code"] = postal_code
    if country:
        addr_obj["country"] = country
    if addr_obj:
        out["addresses"] = json_dumps_sorted([addr_obj])
    else:
        out["addresses"] = ""

    # timestamps
    created = parse_datetime_to_utc_iso(src.get("created_at"))
    updated = parse_datetime_to_utc_iso(src.get("updated_at"))
    out["remote_created_at"] = created
    out["last_activity_at"] = updated

    # unmapped fields
    for col_cfg in HANDSHAKE_TABLES["contacts"]["columns"]:
        if "other" in col_cfg["midlayer_columns"]:
            key = col_cfg["phase2_column"]
            raw = src.get(key)
            if raw is None or raw == "":
                continue
            if key in ("primary", "sms_enabled"):
                b = to_bool(raw)
                if b is not None:
                    unmapped[key] = b
                else:
                    unmapped[key] = raw
            else:
                v = raw
                if isinstance(v, str):
                    v = v.strip()
                unmapped[key] = v

    out["_unmapped"] = json_dumps_sorted(unmapped) if unmapped else ""

    # metadata
    out["remote_was_deleted"] = ""
    out["_source_system"] = source_system
    out["_source_record_id"] = out["external_id"] or str(src.get("id", "")).strip()
    out["_company_id"] = company_id
    out["_ingested_at"] = ingested_at
    out["_source_file"] = source_file
    out["_mapping_version"] = mapping_version

    # row hash
    out["_row_hash"] = compute_row_hash(out, MID_LAYER_COLUMNS_ORDER["contacts"])
    return out


def map_customers_row(src, source_system, company_id, ingested_at, source_file, mapping_version):
    out = {col: "" for col in MID_LAYER_COLUMNS_ORDER["customers"]}
    unmapped = {}

    # external_id
    val = src.get("id", "")
    val = str(val).strip() if val not in (None, "") else ""
    out["external_id"] = val

    # name
    name = src.get("name", "")
    name = str(name).strip()
    out["name"] = name or ""

    # email_address
    email = src.get("email", "")
    email = str(email).strip()
    if email:
        # lowercase domain part only
        if "@" in email:
            local, domain = email.split("@", 1)
            email_norm = f"{local}@{domain.lower()}"
        else:
            email_norm = email
        if EMAIL_REGEX.match(email_norm):
            out["email_address"] = email_norm
        else:
            out["email_address"] = ""
    else:
        out["email_address"] = ""

    # tax_number from tax_id
    tax_id = str(src.get("tax_id", "") or "").strip()
    out["tax_number"] = tax_id or ""

    # currency
    currency = str(src.get("currency", "") or "").strip().upper()
    if currency and CURRENCY_REGEX.match(currency):
        out["currency"] = currency
    else:
        out["currency"] = ""

    # phone_number
    phone = str(src.get("phone", "") or "").strip()
    out["phone_number"] = phone or ""

    # addresses
    addr1 = str(src.get("address1", "") or "").strip()
    addr2 = str(src.get("address2", "") or "").strip()
    city = str(src.get("city", "") or "").strip()
    state = str(src.get("state", "") or "").strip()
    postal_code = str(src.get("postal_code", "") or "").strip()
    country = str(src.get("country", "") or "").strip().upper()
    addr_obj = {}
    if addr1:
        addr_obj["street_1"] = addr1
    if addr2:
        addr_obj["street_2"] = addr2
    if city:
        addr_obj["city"] = city
    if state:
        addr_obj["state"] = state
    if postal_code:
        addr_obj["postal_code"] = postal_code
    if country:
        addr_obj["country"] = country
    if addr_obj:
        out["addresses"] = json_dumps_sorted([addr_obj])
    else:
        out["addresses"] = ""

    # status, is_supplier, is_customer, remote_updated_at left empty (no mapping)
    out["status"] = ""
    out["is_supplier"] = ""
    out["is_customer"] = ""
    out["remote_updated_at"] = ""
    out["remote_was_deleted"] = ""

    # unmapped
    for col_cfg in HANDSHAKE_TABLES["customers"]["columns"]:
        if "other" in col_cfg["midlayer_columns"]:
            key = col_cfg["phase2_column"]
            raw = src.get(key)
            if raw is None or raw == "":
                continue
            v = raw
            if isinstance(v, str):
                v = v.strip()
            if key in ("autopay", "chase", "credit_hold", "taxable"):
                b = to_bool(v)
                unmapped[key] = b if b is not None else v
            elif key == "autopay_delay_days":
                try:
                    unmapped[key] = int(v)
                except Exception:
                    unmapped[key] = v
            elif key == "credit_limit":
                unmapped[key] = money_to_str(v)
            else:
                unmapped[key] = v

    out["_unmapped"] = json_dumps_sorted(unmapped) if unmapped else ""

    # metadata
    out["_source_system"] = source_system
    out["_source_record_id"] = out["external_id"] or str(src.get("id", "")).strip()
    out["_company_id"] = company_id
    out["_ingested_at"] = ingested_at
    out["_source_file"] = source_file
    out["_mapping_version"] = mapping_version

    out["_row_hash"] = compute_row_hash(out, MID_LAYER_COLUMNS_ORDER["customers"])
    return out


def map_invoices_row(src, source_system, company_id, ingested_at, source_file, mapping_version):
    out = {col: "" for col in MID_LAYER_COLUMNS_ORDER["invoices"]}
    unmapped = {}

    # external_id
    val = src.get("id", "")
    val = str(val).strip() if val not in (None, "") else ""
    out["external_id"] = val

    # contact_external_id from customer
    cust = src.get("customer", "")
    cust = str(cust).strip() if cust not in (None, "") else ""
    out["contact_external_id"] = cust

    # number
    num = str(src.get("number", "") or "").strip()
    out["number"] = num

    # currency
    currency = str(src.get("currency", "") or "").strip().upper()
    if currency and CURRENCY_REGEX.match(currency):
        out["currency"] = currency
    else:
        out["currency"] = ""

    # issue_date, due_date from unix timestamps
    out["issue_date"] = unix_to_iso(src.get("date"))
    out["due_date"] = unix_to_iso(src.get("due_date"))

    # subtotal, total, balance
    out["sub_total"] = money_to_str(src.get("subtotal"))
    out["total_amount"] = money_to_str(src.get("total"))
    out["balance"] = money_to_str(src.get("balance"))

    # status from explicit status column
    status_raw = str(src.get("status", "") or "").strip().lower()
    status_mapped = ""
    if status_raw:
        if status_raw == "paid":
            status_mapped = "PAID"
        elif status_raw == "voided":
            status_mapped = "VOID"
        elif status_raw == "past_due":
            status_mapped = "OPEN"
        elif status_raw == "not_sent":
            status_mapped = "DRAFT"
        elif status_raw == "sent":
            status_mapped = "OPEN"
        else:
            # unexpected; leave empty
            status_mapped = ""
    out["status"] = status_mapped

    # draft influences status if not already set
    draft_bool = to_bool(src.get("draft"))
    if draft_bool is True and not out["status"]:
        out["status"] = "DRAFT"

    # paid influences status; cannot infer paid_on_date
    paid_bool = to_bool(src.get("paid"))
    if paid_bool is True and not out["status"]:
        out["status"] = "PAID"

    # memo from name then notes precedence
    name = str(src.get("name", "") or "").strip()
    notes = str(src.get("notes", "") or "").strip()
    memo = ""
    if name:
        memo = name
    if notes:
        # prefer notes; if name also present, concatenate
        if memo and memo != notes:
            memo = f"{memo}\n{notes}"
        else:
            memo = notes
    out["memo"] = memo

    # paid_on_date left empty (no reliable date)
    out["paid_on_date"] = ""

    # type, exchange_rate, total_discount, total_tax_amount, remote_was_deleted left empty
    out["type"] = ""
    out["exchange_rate"] = ""
    out["total_discount"] = ""
    out["total_tax_amount"] = ""
    out["remote_was_deleted"] = ""

    # unmapped fields
    for col_cfg in HANDSHAKE_TABLES["invoices"]["columns"]:
        if "other" in col_cfg["midlayer_columns"]:
            key = col_cfg["phase2_column"]
            raw = src.get(key)
            if raw is None or raw == "":
                continue
            v = raw
            if isinstance(v, str):
                v = v.strip()
            if key in ("autopay", "closed", "paid"):
                b = to_bool(v)
                unmapped[key] = b if b is not None else v
            elif key == "attempt_count":
                try:
                    unmapped[key] = int(v)
                except Exception:
                    unmapped[key] = v
            elif key == "next_payment_attempt":
                iso = unix_to_iso(v)
                if iso:
                    unmapped[key] = iso
            else:
                unmapped[key] = v

    # any additional source columns not in handshake for invoices -> unmapped
    known_phase2_cols = {c["phase2_column"] for c in HANDSHAKE_TABLES["invoices"]["columns"]}
    for k, v in src.items():
        if k not in known_phase2_cols:
            if v is None or v == "":
                continue
            val = v.strip() if isinstance(v, str) else v
            unmapped[k] = val

    out["_unmapped"] = json_dumps_sorted(unmapped) if unmapped else ""

    # metadata
    out["_source_system"] = source_system
    out["_source_record_id"] = out["external_id"] or str(src.get("id", "")).strip()
    out["_company_id"] = company_id
    out["_ingested_at"] = ingested_at
    out["_source_file"] = source_file
    out["_mapping_version"] = mapping_version

    out["_row_hash"] = compute_row_hash(out, MID_LAYER_COLUMNS_ORDER["invoices"])
    return out


# ---------------- Main CLI and dispatcher ---------------- #

def parse_args():
    parser = argparse.ArgumentParser(description="Phase 2.5 mid-layer mapper")
    parser.add_argument("--input", required=True, help="Path to source CSV file")
    parser.add_argument("--output", required=True, help="Output directory")
    parser.add_argument(
        "--table",
        required=True,
        choices=["contacts", "customers", "invoices"],
        help="Target table to map",
    )
    # Optional metadata overrides (with sensible defaults)
    parser.add_argument("--source-system", default="invoiced", help="Source system slug")
    parser.add_argument("--company-id", default="unknown-company", help="Company id")
    parser.add_argument(
        "--mapping-version",
        default="invoiced@0.1.0",
        help="Mapping version identifier",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    table = args.table
    if table not in HANDSHAKE_TABLES:
        sys.stderr.write(f"Unsupported table: {table}\n")
        sys.exit(1)

    input_path = Path(args.input)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_csv_path = output_dir / f"{table}_mapped.csv"

    ingested_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    source_file = str(input_path)
    source_system = args.source_system
    company_id = args.company_id
    mapping_version = args.mapping_version

    mapper = {
        "contacts": map_contacts_row,
        "customers": map_customers_row,
        "invoices": map_invoices_row,
    }[table]

    with input_path.open("r", encoding="utf-8", newline="") as f_in, \
            output_csv_path.open("w", encoding="utf-8", newline="") as f_out:
        reader = csv.DictReader(f_in)
        mid_cols = MID_LAYER_COLUMNS_ORDER[table]
        writer = csv.DictWriter(
            f_out,
            fieldnames=mid_cols,
            delimiter=",",
            quotechar='"',
            quoting=csv.QUOTE_MINIMAL,
            lineterminator="\n",
        )
        writer.writeheader()

        for src_row in reader:
            mapped = mapper(
                src_row,
                source_system=source_system,
                company_id=company_id,
                ingested_at=ingested_at,
                source_file=source_file,
                mapping_version=mapping_version,
            )
            writer.writerow({col: mapped.get(col, "") for col in mid_cols})


if __name__ == "__main__":
    main()
