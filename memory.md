# Coding pattern preferences

- Always prefer simple solutions
- Avoid duplication of code whenever possible, which means checking for other areas of the codebase that might already have similar code and functionality
- Write code that takes into account the different environments: dev, test, and prod -- ignore this one if there is just one env
- You are careful to only make changes that are requested or you are confident are well understood and related to the change being requested
- When fixing an issue or bug, do not introduce a new pattern or technology without first exhausting all options for the existing implementation. And if you finally do this, make sure to remove the old implementation afterwards so we don't have duplicate logic.
- Keep the codebase very clean and organized
- Avoid writing scripts in files if possible, especially if the script is likely only to be run once
- Avoid having files over 200-300 lines of code. Refactor at that point.
- Mocking data is only needed for tests, never mock data for dev or prod
- Never add stubbing or fake data patterns to code that affects the dev or prod environments
- Never overwrite my `.env` file without first asking and confirming

## Working memory protocol

- After every interaction, check whether any new durable context should be captured in `memory.md`
- Durable context includes decisions, definitions, constraints, IDs, links, gotchas, preferences, and workflow rules that will matter in later work
- Update `memory.md` immediately when that durable context changes so it stays current and useful
- Before updating `memory.md`, first show the exact proposed memory text in chat, then apply the update
- After making any edit to `memory.md`, always open and display the full file contents in chat so the user can verify the change
- `memory.md` updates should be additive by default; do not rewrite the whole file unless the file does not exist yet or the user explicitly approves a larger restructure
- When proposing a `memory.md` update, show the suggested changes or added lines first, ask for permission, and then apply the update
- Prefer preserving existing memory structure and appending or editing only the smallest relevant section
- Keep notes concise and durable; avoid noisy logs that will not help future work

## Documentation requirements

- After implementing code, always give a high-level overview of the changes made and explain the important technical aspects of the implementation
- Update `README.md` whenever changes affect project structure, workflow, behavior, setup, documentation expectations, or repository usage so the repo documentation stays up to date
- Make sure generated code is well documented and includes useful comments where they help explain non-obvious logic
- If you use an external repo, library, or reference implementation in a meaningful way, explain in the README what was used, how it was used, and why it was used
- Maintain product-oriented documentation in `docs/` that explains from a product perspective what a feature or workflow does, not only the technical implementation details

## Spec workflow

- Before implementing any new feature or meaningful behavior change, create a spec document first
- Save feature specs under `docs/specs/`
- Use the `superpowers:brainstorming` workflow to create specs before implementation
- Treat the approved spec as the implementation reference
- Keep specs concise, explicit, and current with the intended scope

## Session notes

### Durable context

- `memory.md` is the canonical file for durable agent workflow rules in this repo
- `README.md` should stay concise and serve as the human-facing summary of project purpose and process
- `docs/specs/` is the canonical location for feature specs
- Product-oriented documentation should live in `docs/`
- `docs/sources/` is the canonical location for raw source-system data formats (e.g. Invoiced.com, Stripe)
- Invoiced.com source format contract lives at `docs/sources/invoiced-data-format.md`
- Simulated "raw dump" feeders live under `seeds/generators/<source>/` (one sub-package per source)
- Convention for landing nested API fields into a flat sheet/CSV: top-level scalars as columns; nested objects/arrays as JSON strings in a `*_json` column (e.g. `items_json`, `metadata_json`)
- Architecture direction: Supabase Postgres-first. Canonical operational tables are `mid_*` and `target_*`; old CSV sample fixtures remain historical examples only.
- When discussion in chat intentionally diverges from the current written spec, explicitly call out the mismatch, explain whether docs/spec updates are needed, and surface that decision before proceeding as if the new direction is canonical.

### What was tried

- 2026-04-18: Added root `README.md` and `memory.md`
- 2026-04-18: Created a design spec for documentation and process rules in `docs/specs/2026-04-18-documentation-process-rules-design.md`
- 2026-04-18: Created an implementation plan in `docs/superpowers/plans/2026-04-18-documentation-process-rules.md`
- 2026-04-18: Added `docs/sources/invoiced-data-format.md` recording the raw Invoiced.com API shape for Customers, Contacts, and Invoices
- 2026-04-18: Added `seeds/generators/invoiced/` feeder — a 30s-cadence simulator that appends Invoiced-shaped Customers/Contacts/Invoices to Google Sheets with realistic onboarding + lifecycle transitions