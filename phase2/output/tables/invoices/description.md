# Invoices

## Summary
This table contains invoice data for ACME Co., detailing accounts receivable transactions. It includes information about invoice numbers, associated customer IDs, issue and due dates, payment status, and amounts.

## Row meaning
Each row represents a single invoice issued to a customer.

## Relationships
This table likely links to a customers table via the `contact_external_id` field, which represents the customer associated with each invoice.

## Datasource
Filename: uploads/acme-co_invoices_initial_20260418.csv

## Retrieval process
This dataset appears to be a static CSV file, suggesting it was exported from a system like Stripe. It includes metadata such as source system and mapping version, indicating it might be part of a larger data integration process.