# Invoices

## Summary
The Invoices table represents billing documents issued to customers for goods or services provided.

## Row meaning
Each row represents a single invoice issued to a customer.

## Relationships
- Linked to the Customers table via the `customer_id` foreign key.
- May have related entries in the Payments and Credit Notes tables.

## Datasource
Stripe API - Invoices Endpoint

## Retrieval process
Retrieve invoices using the Stripe API's Invoices endpoint. Supports pagination and filtering by customer, status, and date range.