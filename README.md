# ERP Data Ingestion

This repository is for an agentic ERP and data-provider ingestion system that standardizes source data into a mid-layer format and prepares it for downstream loading.

## Current Scope

The current repository includes:
- Django app scaffolding under `apps/django_api/`
- Mid-layer schemas under `schemas/midlayer/v1/`
- Seed datasets under `seeds/`
- Product and phase specs under `docs/`

## Specs

The current project specs live in:
- [`docs/0001-prd.md`](./docs/0001-prd.md)
- [`docs/0002-phase1-midlayer-csv-contract.md`](./docs/0002-phase1-midlayer-csv-contract.md)
- [`docs/discussion/initial-discussion.md`](./docs/discussion/initial-discussion.md)

For now, these documents are the source of truth for product direction and phase-one scope.

Feature and design specs going forward should be added under [`docs/specs/`](./docs/specs/).

## Repository Layout

```text
apps/      Application code and Django project scaffolding
docs/      Product requirements, phase specs, and discussion notes
           - docs/sources/   Raw source-system data formats (e.g. Invoiced.com)
           - docs/specs/     Feature specs authored before implementation
schemas/   Mid-layer schema definitions
seeds/     Example source data and manifests
           - seeds/generators/gsheets_invoice_feeder.py
             Stripe-shaped synthetic invoice feeder (legacy demo).
           - seeds/generators/invoiced/
             Invoiced.com raw-dump feeder — appends Customers, Contacts,
             and Invoices every 30s, simulating a recurring API pull.
             See docs/sources/invoiced-data-format.md for the column contract.
```

## Documentation And Process

- [`memory.md`](./memory.md) is the detailed source of truth for agent workflow rules, durable context, and documentation expectations
- [`docs/specs/`](./docs/specs/) is the canonical location for feature specs created before implementation
- Product-oriented documentation should live in `docs/` alongside technical specs and discussion notes
- This README should be kept up to date as the repository structure, workflow, or behavior changes

## Architecture

TBD.
