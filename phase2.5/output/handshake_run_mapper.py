"""
This script is generated from a handshake artifact to map Phase 2 data to mid-layer tables.
It supports multiple tables: contacts, customers, and invoices. The script reads input CSV files,
applies transformations as specified in the handshake, and outputs formatted mid-layer CSV files.
"""

import argparse
import csv
import json
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

# Define the handshake mapping as a constant
HANDSHAKE_TABLES = {
    "contacts": {
        "columns": [
            {"phase2_column": "external_id", "midlayer_columns": ["external_id"], "processing_steps": ["cast to string"]},
            {"phase2_column": "first_name", "midlayer_columns": ["first_name"], "processing_steps": ["cast to string", "trim whitespace"]},
            {"phase2_column": "last_name", "midlayer_columns": ["last_name"], "processing_steps": ["cast to string", "trim whitespace"]},
            {"phase2_column": "account_external_id", "midlayer_columns": ["account_external_id"], "processing_steps": ["cast to string"]},
            {"phase2_column": "addresses", "midlayer_columns": ["addresses"], "processing_steps": ["minify JSON", "cast to string"]},
            {"phase2_column": "email_addresses", "midlayer_columns": ["email_addresses"], "processing_steps": ["minify JSON", "cast to string"]},
            {"phase2_column": "phone_numbers", "midlayer_columns": ["phone_numbers"], "processing_steps": ["minify JSON", "cast to string"]},
            {"phase2_column": "last_activity_at", "midlayer_columns": ["last_activity_at"], "processing_steps": ["cast to ISO 8601 UTC datetime"]},
            {"phase2_column": "remote_created_at", "midlayer_columns": ["remote_created_at"], "processing_steps": ["cast to ISO 8601 UTC datetime"]},
            {"phase2_column": "remote_was_deleted", "midlayer_columns": ["remote_was_deleted"], "processing_steps": ["cast to boolean"]},
            {"phase2_column": "_unmapped", "midlayer_columns": ["_unmapped"], "processing_steps": ["minify JSON", "cast to string"]},
            {"phase2_column": "_source_system", "midlayer_columns": ["_source_system"], "processing_steps": ["cast to string"]},
            {"phase2_column": "_source_record_id", "midlayer_columns": ["_source_record_id"], "processing_steps": ["cast to string"]},
            {"phase2_column": "_company_id", "midlayer_columns": ["_company_id"], "processing_steps": ["cast to string"]},
            {"phase2_column": "_ingested_at", "midlayer_columns": ["_ingested_at"], "processing_steps": ["cast to ISO 8601 UTC datetime"]},
            {"phase2_column": "_source_file", "midlayer_columns": ["_source_file"], "processing_steps": ["cast to string"]},
            {"phase2_column": "_mapping_version", "midlayer_columns": ["_mapping_version"], "processing_steps": ["cast to string"]},
            {"phase2_column": "_row_hash", "midlayer_columns": ["_row_hash"], "processing_steps": ["cast to string"]},
        ],
        "canonical_order": [
            "external_id", "first_name", "last_name", "account_external_id", "addresses", "email_addresses",
            "phone_numbers", "last_activity_at", "remote_created_at", "remote_was_deleted", "_unmapped",
            "_source_system", "_source_record_id", "_company_id", "_ingested_at", "_source_file",
            "_mapping_version", "_row_hash"
        ]
    },
    "customers": {
        "columns": [
            {"phase2_column": "external_id", "midlayer_columns": ["external_id"], "processing_steps": ["cast to string"]},
            {"phase2_column": "name", "midlayer_columns": ["name"], "processing_steps": ["cast to string"]},
            {"phase2_column": "is_supplier", "midlayer_columns": ["is_supplier"], "processing_steps": ["cast to boolean"]},
            {"phase2_column": "is_customer", "midlayer_columns": ["is_customer"], "processing_steps": ["cast to boolean"]},
            {"phase2_column": "email_address", "midlayer_columns": ["email_address"], "processing_steps": ["cast to string", "validate email format"]},
            {"phase2_column": "tax_number", "midlayer_columns": ["tax_number"], "processing_steps": ["cast to string"]},
            {"phase2_column": "status", "midlayer_columns": ["status"], "processing_steps": ["enum normalization: ACTIVE to ACTIVE, INACTIVE to ARCHIVED"]},
            {"phase2_column": "currency", "midlayer_columns": ["currency"], "processing_steps": ["cast to string", "uppercase", "validate ISO-4217 format"]},
            {"phase2_column": "remote_updated_at", "midlayer_columns": ["remote_updated_at"], "processing_steps": ["cast to datetime", "convert to ISO 8601 UTC"]},
            {"phase2_column": "phone_number", "midlayer_columns": ["phone_number"], "processing_steps": ["cast to string"]},
            {"phase2_column": "addresses", "midlayer_columns": ["addresses"], "processing_steps": ["minify JSON"]},
            {"phase2_column": "remote_was_deleted", "midlayer_columns": ["remote_was_deleted"], "processing_steps": ["cast to boolean"]},
            {"phase2_column": "_unmapped", "midlayer_columns": ["_unmapped"], "processing_steps": ["minify JSON"]},
            {"phase2_column": "_source_system", "midlayer_columns": ["_source_system"], "processing_steps": ["cast to string"]},
            {"phase2_column": "_source_record_id", "midlayer_columns": ["_source_record_id"], "processing_steps": ["cast to string"]},
            {"phase2_column": "_company_id", "midlayer_columns": ["_company_id"], "processing_steps": ["cast to string"]},
            {"phase2_column": "_ingested_at", "midlayer_columns": ["_ingested_at"], "processing_steps": ["cast to datetime", "convert to ISO 8601 UTC"]},
            {"phase2_column": "_source_file", "midlayer_columns": ["_source_file"], "processing_steps": ["cast to string"]},
            {"phase2_column": "_mapping_version", "midlayer_columns": ["_mapping_version"], "processing_steps": ["cast to string"]},
            {"phase2_column": "_row_hash", "midlayer_columns": ["_row_hash"], "processing_steps": ["cast to string"]},
        ],
        "canonical_order": [
            "external_id", "name", "is_supplier", "is_customer", "email_address", "tax_number", "status",
            "currency", "remote_updated_at", "phone_number", "addresses", "remote_was_deleted", "_unmapped",
            "_source_system", "_source_record_id", "_company_id", "_ingested_at", "_source_file",
            "_mapping_version", "_row_hash"
        ]
    },
    "invoices": {
        "columns": [
            {"phase2_column": "external_id", "midlayer_columns": ["external_id"], "processing_steps": ["Trim whitespace", "Ensure prefix 'in_' is preserved"]},
            {"phase2_column": "type", "midlayer_columns": ["type"], "processing_steps": ["Enum normalization to 'ACCOUNTS_RECEIVABLE'"]},
            {"phase2_column": "number", "midlayer_columns": ["number"], "processing_steps": ["Trim whitespace"]},
            {"phase2_column": "contact_external_id", "midlayer_columns": ["contact_external_id"], "processing_steps": ["Trim whitespace", "Ensure prefix 'cus_' is preserved"]},
            {"phase2_column": "issue_date", "midlayer_columns": ["issue_date"], "processing_steps": ["Convert to ISO 8601 UTC format"]},
            {"phase2_column": "due_date", "midlayer_columns": ["due_date"], "processing_steps": ["Convert to ISO 8601 UTC format"]},
            {"phase2_column": "paid_on_date", "midlayer_columns": ["paid_on_date"], "processing_steps": ["Convert to ISO 8601 UTC format"]},
            {"phase2_column": "memo", "midlayer_columns": ["memo"], "processing_steps": ["Trim whitespace"]},
            {"phase2_column": "currency", "midlayer_columns": ["currency"], "processing_steps": ["Convert to uppercase", "Validate against ISO-4217"]},
            {"phase2_column": "exchange_rate", "midlayer_columns": ["exchange_rate"], "processing_steps": ["Convert to string preserving precision"]},
            {"phase2_column": "total_discount", "midlayer_columns": ["total_discount"], "processing_steps": ["Convert to string with 4 decimal places"]},
            {"phase2_column": "sub_total", "midlayer_columns": ["sub_total"], "processing_steps": ["Convert to string with 4 decimal places"]},
            {"phase2_column": "total_tax_amount", "midlayer_columns": ["total_tax_amount"], "processing_steps": ["Convert to string with 4 decimal places"]},
            {"phase2_column": "total_amount", "midlayer_columns": ["total_amount"], "processing_steps": ["Convert to string with 4 decimal places"]},
            {"phase2_column": "balance", "midlayer_columns": ["balance"], "processing_steps": ["Convert to string with 4 decimal places"]},
            {"phase2_column": "status", "midlayer_columns": ["status"], "processing_steps": ["Enum normalization to 'PAID' or 'OPEN'"]},
            {"phase2_column": "remote_was_deleted", "midlayer_columns": ["remote_was_deleted"], "processing_steps": ["Convert to boolean"]},
            {"phase2_column": "_unmapped", "midlayer_columns": ["_unmapped"], "processing_steps": ["Minify JSON"]},
            {"phase2_column": "_source_system", "midlayer_columns": ["_source_system"], "processing_steps": ["Trim whitespace"]},
            {"phase2_column": "_source_record_id", "midlayer_columns": ["_source_record_id"], "processing_steps": ["Trim whitespace", "Ensure prefix 'in_' is preserved"]},
            {"phase2_column": "_company_id", "midlayer_columns": ["_company_id"], "processing_steps": ["Trim whitespace"]},
            {"phase2_column": "_ingested_at", "midlayer_columns": ["_ingested_at"], "processing_steps": ["Convert to ISO 8601 UTC format"]},
            {"phase2_column": "_source_file", "midlayer_columns": ["_source_file"], "processing_steps": ["Trim whitespace"]},
            {"phase2_column": "_mapping_version", "midlayer_columns": ["_mapping_version"], "processing_steps": ["Trim whitespace"]},
            {"phase2_column": "_row_hash", "midlayer_columns": ["_row_hash"], "processing_steps": ["Trim whitespace"]},
        ],
        "canonical_order": [
            "external_id", "type", "number", "contact_external_id", "issue_date", "due_date", "paid_on_date",
            "memo", "currency", "exchange_rate", "total_discount", "sub_total", "total_tax_amount",
            "total_amount", "balance", "status", "remote_was_deleted", "_unmapped", "_source_system",
            "_source_record_id", "_company_id", "_ingested_at", "_source_file", "_mapping_version", "_row_hash"
        ]
    }
}

def process_value(value, steps):
    """Process a value according to the specified processing steps."""
    for step in steps:
        if step == "cast to string":
            value = str(value) if value is not None else ""
        elif step == "trim whitespace":
            value = value.strip() if value else ""
        elif step == "minify JSON":
            value = json.dumps(json.loads(value), separators=(',', ':')) if value else ""
        elif step == "cast to ISO 8601 UTC datetime":
            value = datetime.fromisoformat(value).strftime('%Y-%m-%dT%H:%M:%SZ') if value else ""
        elif step == "cast to boolean":
            value = "true" if value.lower() in ["true", "1"] else "false"
        elif step == "Convert to string with 4 decimal places":
            value = f"{Decimal(value):.4f}" if value else ""
        elif step == "Convert to uppercase":
            value = value.upper() if value else ""
        elif step == "Convert to string preserving precision":
            value = str(value) if value else ""
        elif step.startswith("Enum normalization"):
            if "ACTIVE" in step and value == "INACTIVE":
                value = "ARCHIVED"
            elif "PAID" in step and value not in ["PAID", "OPEN"]:
                value = "OPEN"
        elif step.startswith("Ensure prefix"):
            prefix = step.split("'")[1]
            if not value.startswith(prefix):
                value = prefix + value
    return value

def map_row(row, table_config):
    """Map a single row from Phase 2 to mid-layer format."""
    mapped_row = {}
    unmapped = {}
    for column in table_config["columns"]:
        phase2_col = column["phase2_column"]
        midlayer_cols = column["midlayer_columns"]
        processing_steps = column["processing_steps"]
        if phase2_col in row:
            value = row[phase2_col]
            processed_value = process_value(value, processing_steps)
            for midlayer_col in midlayer_cols:
                if midlayer_col == "_unmapped":
                    unmapped[phase2_col] = processed_value
                else:
                    mapped_row[midlayer_col] = processed_value
        else:
            unmapped[phase2_col] = ""
    mapped_row["_unmapped"] = json.dumps(unmapped, separators=(',', ':')) if unmapped else ""
    return mapped_row

def write_output(rows, output_path, table_config):
    """Write the mapped rows to a CSV file in the mid-layer format."""
    with open(output_path, mode='w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=table_config["canonical_order"], quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

def main():
    parser = argparse.ArgumentParser(description="Map Phase 2 CSV data to mid-layer format.")
    parser.add_argument('--input', required=True, help='Path to the input CSV file.')
    parser.add_argument('--output', required=True, help='Path to the output directory or file.')
    parser.add_argument('--table', required=True, choices=HANDSHAKE_TABLES.keys(), help='Table to process (contacts, customers, invoices).')
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    table_name = args.table

    if not input_path.exists():
        print(f"Input file {input_path} does not exist.", file=sys.stderr)
        sys.exit(1)

    table_config = HANDSHAKE_TABLES[table_name]

    with open(input_path, mode='r', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        mapped_rows = [map_row(row, table_config) for row in reader]

    if output_path.is_dir():
        output_file = output_path / f"{table_name}_mapped.csv"
    else:
        output_file = output_path

    write_output(mapped_rows, output_file, table_config)

if __name__ == "__main__":
    main()
