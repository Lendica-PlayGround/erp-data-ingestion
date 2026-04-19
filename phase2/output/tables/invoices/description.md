# Invoices

## Summary
Customer billing documents exported from Invoiced.com for Div’s Furniture Manufacturing Co, including status, amounts, key dates, and links back to the source system.

## Row meaning
Each row represents a single invoice issued to a customer in Invoiced.com.

## Relationships
- `customer` links to `customers.id` in the `customers` sheet/table.
- JSON fields (`items_json`, `discounts_json`, `taxes_json`, `ship_to_json`, `metadata_json`) can be exploded into separate detail tables if needed (e.g., invoice line items, taxes, shipping address, custom metadata).

## Datasource
- File: `uploads/Div_s_Furniture_Manufacturing_Co.xlsx`
- Worksheet: `invoices`
- Source system noted in `meta` sheet as Invoiced.com.

## Retrieval process
This dataset is provided as an Excel export. To refresh it:
- Pull the latest `Div_s_Furniture_Manufacturing_Co.xlsx` export from Invoiced.com (or the connected Google Sheet described in the `meta` sheet).
- Read the `invoices` worksheet as a flat table.
- There is no in-file pagination; all invoices are contained in a single sheet.
- For incremental ingestion, use `updated_at` as the cursor field to detect new or changed invoices.