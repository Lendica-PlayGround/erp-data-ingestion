# ERP Data Ingestion

This repository is for an agentic ERP and data-provider ingestion system that standardizes source data into a mid-layer format and prepares it for downstream loading.

## Current Scope

The current repository includes:
- Django app scaffolding under `apps/django_api/`
- **Mira** (Phase 2–3 agent) under [`mira/`](./mira/) — see [`mira/README.md`](./mira/README.md)
- Seed datasets under `seeds/`
- Product and phase specs under `docs/`

## Specs

The current project specs live in:
- [`docs/0001-prd.md`](./docs/0001-prd.md)
- [`docs/0002-phase1-midlayer-db-contract.md`](./docs/0002-phase1-midlayer-db-contract.md)
- [`docs/0005-phase4-5-observability-validation.md`](./docs/0005-phase4-5-observability-validation.md)
- [`docs/discussion/initial-discussion.md`](./docs/discussion/initial-discussion.md)

For now, these documents are the source of truth for product direction and phase-one scope.

Feature and design specs going forward should be added under [`docs/specs/`](./docs/specs/).

## Repository Layout

```text
mira/      Phase 2–3 Mira agent: LangGraph runtime, skills, framework, schemas, SQL, tests
apps/      Application code and Django project scaffolding
docs/      Product requirements, phase specs, and discussion notes
           - docs/sources/   Raw source-system data formats (e.g. Invoiced.com)
           - docs/specs/     Feature specs authored before implementation
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

Phase 2–3 **Mira** is isolated under [`mira/`](./mira/):

- `mira/agent/mira/*.md` — bootstrap persona and operating rules (OpenClaw-inspired).
- `mira/agent/skills/<id>/SKILL.md` — skill catalog; tools in `mira/agent/runtime/tools.py`.
- `mira/agent/runtime/` — LangGraph graph, Telegram binding, CLI (`mira`), optional JWT dashboard.
- `mira/framework/` — shared connector library; generated code lands in `mira/connectors/` or the run workspace.
- `mira/schemas/midlayer/v1/` — canonical JSON Schema; `mira/schemas/mapping_contract/v1.schema.json` validates Phase 2.5 contracts.
- `mira/supabase/migrations/` — `onboarding_runs`, `mid_*`, `target_*`, and load-metadata SQL.
- `mira/supabase/load_mid_from_mapper.py` — runs the generated handshake mapper, writes a validation report, uploads replay artifacts plus a manifest to Supabase Storage via the S3 endpoint, records batch metadata/run events, and upserts the resulting mid CSV into Supabase Postgres.
- `mira/supabase/load_target_from_mid.py` — promotes `mid_*` rows into `target_*` tables using the current relational transform contract.

## Current Phase 4/5 Slice

The first Phase 4/5 runtime slice is now implemented:

- [`.env.example`](./.env.example) documents the ClickHouse and Supabase Storage env contract.
- [`mira/framework/csv_writer.py`](./mira/framework/csv_writer.py) builds replay-oriented artifact manifests with checksums and storage keys.
- [`mira/framework/observability.py`](./mira/framework/observability.py) shapes normalized run-event payloads and publishes loader events into ClickHouse.
- [`mira/supabase/load_mid_from_mapper.py`](./mira/supabase/load_mid_from_mapper.py) now requires `MIRA_RUN_ID`, uploads raw/mapped/validation artifacts to Supabase Storage, persists manifest metadata into `ingestion_load_batches.metadata`, emits a `run_events` record to ClickHouse, and fails closed when any validation failure is present.
- [`mira/supabase/load_target_from_mid.py`](./mira/supabase/load_target_from_mid.py) promotes `mid_*` rows into `target_*` tables so the current repo has a runnable mid-to-target path.
- [`docs/0005-phase4-5-observability-validation.md`](./docs/0005-phase4-5-observability-validation.md) is the implementation-ready spec for the remaining Phase 4/5 work.

Install locally from repo root: `pip install -e ".[dev]"` (optional: `[supabase]`, `[dashboard]`). Entrypoint: `mira --help`.
