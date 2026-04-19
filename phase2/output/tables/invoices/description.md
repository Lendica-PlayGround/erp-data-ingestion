# Invoices

## Summary
This table contains invoice data for Acme Co., detailing accounts receivable transactions. It includes information about invoice numbers, dates, amounts, and statuses.

## Row meaning
Each row represents a single invoice issued to a customer.

## Relationships
This table links to customer data through the `contact_external_id` field, which serves as a foreign key to identify the customer associated with each invoice.

## Datasource
Filename: uploads/acme-co_invoices_initial_20260418.csv

## Retrieval process
This dataset is retrieved from a CSV file, which appears to be a static export from a system like Stripe. There is no indication of pagination or filtering as it is a file-based dataset.