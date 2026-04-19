# Invoiced.com Raw Source Data Format

This document records the **raw** shape of the data pulled from
[Invoiced.com's public API](https://developer.invoiced.com/) for the three
entities this project currently ingests:

- **Customers** — `GET /customers` — <https://developer.invoiced.com/api/customers>
- **Contacts**  — `GET /customers/:customer_id/contacts` — <https://developer.invoiced.com/api/contacts>
- **Invoices**  — `GET /invoices` — <https://developer.invoiced.com/api/invoices>

It is the *source-side* contract: anything produced by
`seeds/generators/invoiced/` (the simulated "raw dump" feeder) MUST conform to
this shape, and any downstream mapper/ingestor MUST be prepared to receive
exactly these fields, with the same types, nullability, and edge cases.

Nothing in this document is invented: every field below is taken directly
from the Invoiced docs. Project-specific conventions (flattening to CSV,
JSON-in-a-column, etc.) are called out explicitly.

---

## Conventions used when we "dump" this data to a sheet/CSV

Invoiced responses are JSON. When we land them into a Google Sheet
(one row per entity per worksheet) we apply three rules:

1. **Top-level scalar fields become columns**, in the order defined in each
   entity section below. Column names match the JSON keys exactly
   (`snake_case`, no renaming).
2. **Nested objects / arrays are serialized as a single JSON string**
   in one column (suffix `_json`). This preserves fidelity without expanding
   into separate sheets. Examples: `items_json`, `taxes_json`, `ship_to_json`,
   `metadata_json`, `payment_source_json`.
3. **Timestamps stay as Unix seconds (integers)** exactly as Invoiced
   returns them. No timezone conversion at the dump layer.

All monetary amounts from Invoiced are **decimal numbers in the invoice's
currency's major units** (e.g. `51.15` means $51.15). This differs from the
Stripe dump feeder (`gsheets_invoice_feeder.py`) which uses integer cents.

---

## 1. Customer

Represents the entity being billed (an organization or a person). Full spec:
<https://developer.invoiced.com/api/customers>

### Example (raw JSON)

```json
{
    "id": 15444,
    "object": "customer",
    "number": "CUST-0001",
    "name": "Acme",
    "email": "[email protected]",
    "type": "company",
    "autopay": true,
    "autopay_delay_days": null,
    "payment_terms": "NET 30",
    "payment_source": {
        "brand": "Visa",
        "exp_month": 2,
        "exp_year": 20,
        "funding": "credit",
        "id": 850,
        "last4": "4242",
        "object": "card"
    },
    "attention_to": null,
    "address1": null,
    "address2": null,
    "city": null,
    "state": null,
    "postal_code": null,
    "country": "US",
    "language": null,
    "currency": null,
    "chase": true,
    "chasing_cadence": null,
    "next_chase_step": null,
    "phone": null,
    "credit_hold": false,
    "credit_limit": null,
    "owner": null,
    "taxable": true,
    "taxes": [],
    "tax_id": null,
    "avalara_entity_use_code": null,
    "avalara_exemption_number": null,
    "parent_customer": null,
    "notes": null,
    "sign_up_page": null,
    "sign_up_url": null,
    "statement_pdf_url": "https://dundermifflin.invoiced.com/statements/t3NmhUomra3g3ueSNnbtUgrr/pdf",
    "ach_gateway": null,
    "cc_gateway": null,
    "metadata": {
        "account_rep": "Jan",
        "icp_number": "1234567890"
    },
    "created_at": 1415222128,
    "updated_at": 1415222128
}
```

### Field reference

| Column                     | Type      | Notes                                                                |
| -------------------------- | --------- | -------------------------------------------------------------------- |
| `id`                       | integer   | Unique customer ID (Invoiced-assigned).                              |
| `object`                   | string    | Always `"customer"`.                                                 |
| `number`                   | string    | Human-facing reference, e.g. `CUST-0001`.                            |
| `name`                     | string    | Customer name.                                                       |
| `email`                    | string    | Primary email.                                                       |
| `type`                     | string    | `"company"` or `"person"`.                                           |
| `autopay`                  | boolean   | AutoPay enabled?                                                     |
| `autopay_delay_days`       | integer   | Days to delay AutoPay, nullable.                                     |
| `payment_terms`            | string    | e.g. `NET 30`. Inherited by invoices when unset on invoice.          |
| `attention_to`             | string    | ATTN: line on addresses, nullable.                                   |
| `address1`                 | string    | Street line 1, nullable.                                             |
| `address2`                 | string    | Street line 2, nullable.                                             |
| `city`                     | string    | Nullable.                                                            |
| `state`                    | string    | State/province, nullable.                                            |
| `postal_code`              | string    | Zip/postal code, nullable.                                           |
| `country`                  | string    | ISO-3166-1 alpha-2, e.g. `US`.                                       |
| `language`                 | string    | ISO-639-1, nullable.                                                 |
| `currency`                 | string    | ISO-4217 (lowercase), nullable — falls back to the account default.  |
| `phone`                    | string    | Nullable.                                                            |
| `chase`                    | boolean   | Collection chasing enabled?                                          |
| `chasing_cadence`          | integer   | Cadence ID, nullable.                                                |
| `next_chase_step`          | integer   | Cadence step ID, nullable.                                           |
| `credit_hold`              | boolean   | When true, new invoices/payments are blocked.                        |
| `credit_limit`             | number    | Nullable.                                                            |
| `owner`                    | integer   | Internal user ID, nullable.                                          |
| `taxable`                  | boolean   | Whether customer is taxable.                                         |
| `tax_id`                   | string    | Printed on documents, nullable.                                      |
| `avalara_entity_use_code`  | string    | Nullable.                                                            |
| `avalara_exemption_number` | string    | Nullable.                                                            |
| `parent_customer`          | integer   | Parent customer ID, nullable (used for sub-accounts / consolidation).|
| `notes`                    | string    | Private notes, nullable.                                             |
| `sign_up_page`             | integer   | Sign-Up Page ID, nullable.                                           |
| `sign_up_url`              | string    | Nullable.                                                            |
| `statement_pdf_url`        | string    | Latest account statement PDF.                                        |
| `ach_gateway`              | integer   | Gateway config ID, nullable.                                         |
| `cc_gateway`               | integer   | Gateway config ID, nullable.                                         |
| `created_at`               | timestamp | Unix seconds.                                                        |
| `updated_at`               | timestamp | Unix seconds.                                                        |
| `payment_source_json`      | JSON      | Serialized `payment_source` object (card/ACH) or `null`.             |
| `taxes_json`               | JSON      | Serialized `taxes` array of Tax Rate IDs (usually `[]`).             |
| `metadata_json`            | JSON      | Serialized `metadata` object (free-form key/value pairs).            |

---

## 2. Contact

A contact is attached to a customer — typically an AP email copy recipient,
a shipping address contact, etc. Full spec:
<https://developer.invoiced.com/api/contacts>

### Example (raw JSON)

```json
{
    "id": 10403,
    "object": "contact",
    "name": "Nancy Talty",
    "title": null,
    "email": "[email protected]",
    "phone": null,
    "primary": true,
    "sms_enabled": null,
    "department": null,
    "address1": null,
    "address2": null,
    "city": null,
    "state": null,
    "postal_code": null,
    "country": null,
    "created_at": 1463510889,
    "updated_at": 1463510889
}
```

### Field reference

Contacts are scoped under a customer in the API
(`GET /customers/:customer_id/contacts`), but the response body does NOT
include `customer_id`. When we dump contacts to a single sheet we **add a
`customer` column** (foreign key to `customer.id`) as the first column so
downstream joins work.

| Column        | Type      | Notes                                                                   |
| ------------- | --------- | ----------------------------------------------------------------------- |
| `customer`    | integer   | **Project-added FK** to `customer.id`. Not part of Invoiced's response. |
| `id`          | integer   | Unique contact ID.                                                      |
| `object`      | string    | Always `"contact"`.                                                     |
| `name`        | string    | Contact name.                                                           |
| `title`       | string    | Job title, nullable.                                                    |
| `email`       | string    | Email, nullable.                                                        |
| `phone`       | string    | Nullable.                                                               |
| `primary`     | boolean   | When true, CC'd on all account communications.                          |
| `sms_enabled` | boolean   | When true, eligible for SMS.                                            |
| `department`  | string    | Nullable.                                                               |
| `address1`    | string    | Nullable.                                                               |
| `address2`    | string    | Nullable.                                                               |
| `city`        | string    | Nullable.                                                               |
| `state`       | string    | Nullable.                                                               |
| `postal_code` | string    | Nullable.                                                               |
| `country`     | string    | ISO-3166-1 alpha-2, nullable.                                           |
| `created_at`  | timestamp | Unix seconds.                                                           |
| `updated_at`  | timestamp | Unix seconds.                                                           |

---

## 3. Invoice

A balance owed to you by a customer, with line items. Full spec:
<https://developer.invoiced.com/api/invoices>

### Example (raw JSON)

```json
{
    "id": 46225,
    "object": "invoice",
    "customer": 15444,
    "name": null,
    "number": "INV-0016",
    "autopay": false,
    "currency": "usd",
    "draft": false,
    "closed": false,
    "paid": false,
    "status": "not_sent",
    "attempt_count": 0,
    "next_payment_attempt": null,
    "subscription": null,
    "date": 1416290400,
    "due_date": 1417500000,
    "payment_terms": "NET 14",
    "purchase_order": null,
    "items": [
        {
            "id": 7, "object": "line_item",
            "name": "Copy Paper, Case", "description": null,
            "catalog_item": null, "type": "product",
            "quantity": 1, "unit_cost": 45, "amount": 45,
            "discountable": true, "discounts": [],
            "taxable": true, "taxes": [],
            "metadata": []
        },
        {
            "id": 8, "object": "line_item",
            "name": "Delivery", "description": null,
            "catalog_item": "delivery", "type": "service",
            "quantity": 1, "unit_cost": 10, "amount": 10,
            "discountable": true, "discounts": [],
            "taxable": true, "taxes": [],
            "metadata": []
        }
    ],
    "notes": null,
    "subtotal": 55,
    "discounts": [],
    "taxes": [
        { "id": 20554, "object": "tax", "amount": 3.85, "tax_rate": null }
    ],
    "total": 51.15,
    "balance": 51.15,
    "ship_to": null,
    "payment_plan": null,
    "url": "https://dundermifflin.invoiced.com/invoices/IZmXbVOPyvfD3GPBmyd6FwXY",
    "payment_url": "https://dundermifflin.invoiced.com/invoices/IZmXbVOPyvfD3GPBmyd6FwXY/payment",
    "pdf_url": "https://dundermifflin.invoiced.com/invoices/IZmXbVOPyvfD3GPBmyd6FwXY/pdf",
    "metadata": [],
    "created_at": 1415229884,
    "updated_at": 1415229884
}
```

### Field reference

| Column                 | Type      | Notes                                                                                                                          |
| ---------------------- | --------- | ------------------------------------------------------------------------------------------------------------------------------ |
| `id`                   | integer   | Unique invoice ID.                                                                                                             |
| `object`               | string    | Always `"invoice"`.                                                                                                            |
| `customer`             | integer   | FK to `customer.id`.                                                                                                           |
| `name`                 | string    | Internal name, defaults to `null`.                                                                                             |
| `number`               | string    | Human reference, e.g. `INV-0016`.                                                                                              |
| `autopay`              | boolean   | AutoPay enabled? Inherited from customer when unset.                                                                           |
| `currency`             | string    | ISO-4217, lowercase (e.g. `usd`).                                                                                              |
| `draft`                | boolean   | `true` ⇒ draft (not outstanding yet).                                                                                          |
| `closed`               | boolean   | `true` ⇒ closed / bad-debt; no more payments allowed.                                                                          |
| `paid`                 | boolean   | `true` ⇒ fully paid.                                                                                                           |
| `status`               | string    | One of: `draft`, `not_sent`, `sent`, `viewed`, `past_due`, `pending`, `paid`, `voided`.                                        |
| `attempt_count`        | integer   | # of charge attempts.                                                                                                          |
| `next_payment_attempt` | timestamp | Next AutoPay charge attempt, nullable.                                                                                         |
| `subscription`         | integer   | Subscription ID if this invoice came from one, nullable.                                                                       |
| `date`                 | timestamp | Invoice date (unix seconds).                                                                                                   |
| `due_date`             | timestamp | Due date (unix seconds).                                                                                                       |
| `payment_terms`        | string    | e.g. `NET 14`.                                                                                                                 |
| `purchase_order`       | string    | Customer PO #, nullable.                                                                                                       |
| `notes`                | string    | Nullable.                                                                                                                      |
| `subtotal`             | number    | Major-units decimal.                                                                                                           |
| `total`                | number    | Major-units decimal.                                                                                                           |
| `balance`              | number    | Outstanding balance (major-units). `0` when paid.                                                                              |
| `payment_plan`         | integer   | Payment plan ID, nullable.                                                                                                     |
| `url`                  | string    | Billing-portal URL.                                                                                                            |
| `payment_url`          | string    | Payment page URL.                                                                                                              |
| `pdf_url`              | string    | PDF download URL.                                                                                                              |
| `created_at`           | timestamp | Unix seconds.                                                                                                                  |
| `updated_at`           | timestamp | Unix seconds.                                                                                                                  |
| `items_json`           | JSON      | Serialized array of Line Item objects. See schema below.                                                                       |
| `discounts_json`       | JSON      | Serialized array of Discount objects (invoice-level).                                                                          |
| `taxes_json`           | JSON      | Serialized array of Tax objects (invoice-level).                                                                               |
| `ship_to_json`         | JSON      | Serialized Shipping Details object or `null`.                                                                                  |
| `metadata_json`        | JSON      | Serialized metadata object.                                                                                                    |

### 3a. Line Item (`items` array)

```json
{
    "id": 8,
    "object": "line_item",
    "catalog_item": "delivery",
    "type": "service",
    "name": "Delivery",
    "description": null,
    "quantity": 1,
    "unit_cost": 10,
    "amount": 10,
    "discountable": true,
    "discounts": [],
    "taxable": true,
    "taxes": [],
    "metadata": []
}
```

`amount = quantity * unit_cost` (Invoiced computes this server-side).
`type` is typically `product`, `service`, or `plan`.

### 3b. Discount (`discounts` array)

```json
{ "id": 20553, "object": "discount", "amount": 5, "coupon": null, "expires": null }
```

### 3c. Tax (`taxes` array)

```json
{ "id": 20554, "object": "tax", "amount": 3.85, "tax_rate": null }
```

### 3d. Shipping Detail (`ship_to`)

```json
{
    "name": "Myron Williams",
    "attention_to": null,
    "address1": "2548 Bottom Lane",
    "address2": null,
    "city": "Monument Beach",
    "state": "MA",
    "postal_code": "02553",
    "country": "US"
}
```

---

## Lifecycle semantics (what a "real-world" dump looks like over time)

When pulling `updated_after=<last_run_ts>` on a recurring schedule, the same
invoice row can reappear many times with a different `status` /
`updated_at`. Typical progression:

```
draft → not_sent → sent → viewed → paid
                              ↘ past_due → paid
           any non-paid  ──→ voided
```

Customers can also be updated in place (e.g. `credit_hold` flipped,
`payment_terms` changed, a new `payment_source` attached). Contacts can be
added, updated (email change), or removed. The simulated feeder in
`seeds/generators/invoiced/` reproduces all of these transitions so
downstream delta ingestion has both INSERTs and UPDATEs to process.

---

## Source-of-truth links

- Customers: <https://developer.invoiced.com/api/customers>
- Contacts:  <https://developer.invoiced.com/api/contacts>
- Invoices:  <https://developer.invoiced.com/api/invoices>
