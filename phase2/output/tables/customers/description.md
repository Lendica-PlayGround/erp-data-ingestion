# Customers

## Summary
The Customers table contains information about individuals or businesses that have made purchases or transactions.

## Row meaning
Each row represents a single customer.

## Relationships
- Linked to the Invoices table via the `customer_id` primary key.
- May have related entries in the Payments and Subscriptions tables.

## Datasource
Stripe API - Customers Endpoint

## Retrieval process
Retrieve customers using the Stripe API's Customers endpoint. Supports pagination and filtering by email, created date, and more.