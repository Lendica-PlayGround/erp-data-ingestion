# Contacts

## Summary
Customer contact records synchronized from Invoiced.com. Represents individual people associated with customer accounts for billing, finance, procurement, and operations.

## Row meaning
Each row represents a single contact person tied to a customer, including role, communication details, and address.

## Relationships
- `customer` is a foreign key to `customers.id` (customer-to-contact = 1-to-many).

## Datasource
- File: `Div_s_Furniture_Manufacturing_Co.xlsx`
- Sheet: `contacts`
- Upstream system noted in `meta` sheet as Invoiced.com.

## Retrieval process
In the Excel context this is a static extract. In the source Invoiced API this would typically come from a `GET /contacts` or `GET /customers/{id}/contacts` endpoint with pagination and `updated_at` for incrementals. For this workbook, ingestion is a full refresh of the `contacts` sheet on each pull.