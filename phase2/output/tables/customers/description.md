# Customers

## Summary
Customer master data synchronized from Invoiced.com for Div’s Furniture Manufacturing Co. Represents organizations and people that purchase furniture and receive invoices.

## Row meaning
Each row represents a single customer account in Invoiced (company or person), including billing profile, credit settings, tax configuration, and statement URLs.

## Relationships
- `id` links to `contacts.customer` (customer-to-contact = 1-to-many).
- `id` links to `invoices.customer` (customer-to-invoice = 1-to-many).
- `parent_customer` can reference another `customers.id` for hierarchical customer structures.

## Datasource
- File: `Div_s_Furniture_Manufacturing_Co.xlsx`
- Sheet: `customers`
- Upstream system noted in `meta` sheet as Invoiced.com.

## Retrieval process
In the Excel context this is a static extract. In the source Invoiced API this would typically come from a `GET /customers` endpoint with cursor or page-based pagination, filterable by `updated_at` for incremental loads. For this workbook, ingestion is a full refresh of the `customers` sheet on each pull.