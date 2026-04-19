# Invoices

## Summary
Sales invoices exported from Invoiced.com for Div’s Furniture Manufacturing Co. Represents billing documents issued to customers for furniture sales and related charges.

## Row meaning
Each row represents a single invoice, including status, dates, monetary amounts, links to hosted documents, and embedded JSON for line items, discounts, taxes, and shipping.

## Relationships
- `customer` is a foreign key to `customers.id` (customer-to-invoice = 1-to-many).
- Line items, discounts, taxes, and shipping addresses are stored as JSON blobs (`items_json`, `discounts_json`, `taxes_json`, `ship_to_json`) and would typically be normalized into separate tables.

## Datasource
- File: `Div_s_Furniture_Manufacturing_Co.xlsx`
- Sheet: `invoices`
- Upstream system noted in `meta` sheet as Invoiced.com.

## Retrieval process
In the Excel context this is a static extract. In the source Invoiced API this would typically come from a `GET /invoices` endpoint with pagination and filters such as `updated_at` or `date` for incremental loads. For this workbook, ingestion is a full refresh of the `invoices` sheet on each pull.