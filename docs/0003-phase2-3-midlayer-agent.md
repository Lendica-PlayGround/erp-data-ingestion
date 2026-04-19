# Phase 2 / 2.5 / 3: AI Forward Engineer for ERP Ingestion

**Date:** April 18, 2026
**Scope:** End-to-end product + technical spec for the agent that drives source onboarding (Phase 2 Discovery), mapping negotiation (Phase 2.5 Handshake), and implementation execution (Phase 3) — producing mid-layer CSVs that conform to the Phase 1 contract.
**References:** `docs/0001-prd.md`, `docs/0002-phase1-midlayer-csv-contract.md`, `docs/discussion/jerry-discussion-midlayer-openclaw.md`, `docs/sources/invoiced-data-format.md`

**Implementation in this repo:** runtime code, skills, framework, schemas, and SQL live under [`mira/`](../mira/README.md) (paths like `agent/skills/` in the sections below map to `mira/agent/skills/`).

---

## 1. Product Vision

Build an **AI Forward Engineer** ("Mira") that fully automates onboarding **any** external data source or legacy ERP system into the merge.dev-aligned mid-layer CSVs defined in `0002-phase1-midlayer-csv-contract.md`. *(Note: While Stripe, Epicor, and Invoiced.com are frequently cited as examples throughout this document, the system is fundamentally source-agnostic and designed to research and adapt to any unknown API, database, or flat-file format).*

This is **a stateful, guided workflow wrapped in a chat surface** — not a freeform chatbot. The chat is the UI; underneath sits a strict state machine, a research engine, and a deterministic codegen pipeline.

### 1.1 Roles

| Role | Who | Responsibility |
| :--- | :--- | :--- |
| **Mira** (AI Implementation Specialist) | Agent | Drives the onboarding. Asks targeted questions, researches the source, proposes the mapping, writes the connector code, opens the PR, runs the syncs. |
| **Forward Deployment Engineer (FDE)** | Internal human | Safety rail. Reviews confidence scores, approves the mapping contract, approves the implementation plan before codegen, monitors the dashboard. |
| **Client / Customer** | External user | Provides credentials, answers domain questions ("Where do you store custom discount tags?"), confirms business meaning of the mapping. |

The product loop is: **AI leads → human approves at two explicit gates → AI executes**. The human should never be the operator.

### 1.2 Phase responsibilities at a glance

| Phase | Mira's role | Output | Gate |
| :--- | :--- | :--- | :--- |
| 2 — Discovery | Discovery + schema-understanding assistant | Structured source profile + per-table / per-column descriptions | (none — flows into 2.5) |
| 2.5 — Handshake | Mapping negotiator | Mapping contract JSON + Implementation Readiness Review (markdown) | **Customer** confirms business meaning + **FDE** confirms implementation |
| 3 — Execution | Implementation engineer | Connector package (code) + initial & delta CSVs in Supabase + dashboard | (none — runs after Phase 2.5 gate) |

### 1.3 Key User Story: The "Telegram Group Chat" Experience

The entire onboarding feels like a collaborative, 3-way **Telegram group chat** between the **User (Client)**, the **AI Agent (Mira)**, and the **Human Agent (FDE)**. Each onboarding run gets its **own dedicated Telegram group**, isolated from every other customer's onboarding (this mimics OpenClaw's per-group session model — see §2.4).

1. **Proactive engagement.** The FDE creates a Telegram group for the new customer, adds Mira's bot and the customer. Mira fires the `BOOTSTRAP.md` ritual: introduces herself ("Hi, I'm Mira — I'll help set up your data ingestion. I'll ask a few questions, inspect your source materials, and propose a mapping before anything runs."), asks what ERP system they use, and requests the API keys or data dumps. While waiting, she autonomously researches the ERP's docs, API spec, and known gotchas using her research skill.
2. **The action plan.** Once Mira understands the source, she drafts a mapping and posts the "Implementation Readiness Review" (IRR) directly into the group as a structured message. Customer and FDE review it inline. Either can ask follow-up questions in the group; Mira responds in-thread.
3. **Two-action approval, in-chat.** Customer types `/approve_customer` to confirm business meaning. FDE types `/approve_fde` to confirm implementation. Both slash commands are owner-gated (mimicking an allowlist group policy) so a random group member cannot trigger codegen.
4. **Execution & code generation.** Upon both approvals, Mira springs into action with structured verbosity: each Phase 3 step posts a chat message with inputs/outputs/links. She sends the customer a final action guide if any manual steps remain (e.g., on-prem export), generates the markdown contracts, writes the Python connector code in her workspace, and commits it via a GitHub Pull Request — link dropped in the group.
5. **Live sync & JWT dashboard.** Mira executes the dry run, then the initial historical CSV dump, then configures the daily delta CSV cron. She posts a **magic JWT auto-login link** scoped to `(company_id, run_id)` into the group. The customer and FDE can click it at any time to see live run logs, row counts, validation results, and data health — without needing to manage separate credentials.
6. **Steady state.** The group stays alive after onboarding. Daily delta-sync summaries post into the group. If a sync fails or anomaly fires, Mira pings the FDE in-group with `@FDE` and proposes a fix.

---

## 2. System Architecture

### 2.1 Layered architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Telegram group chat  (one group per onboarding run)            │
│  Members: Customer, Mira (bot), FDE.  Mention-gated activation. │
├─────────────────────────────────────────────────────────────────┤
│  Custom Agent Runtime (LangGraph-based, OpenClaw-inspired)      │
│   • Bootstrap files: AGENTS.md, IDENTITY.md, SOUL.md,           │
│     USER.md, TOOLS.md, BOOTSTRAP.md (see §2.6)                  │
│   • Per-group session JSONL (see §2.7)                          │
│   • Per-run workspace + sandbox (see §2.7)                      │
├─────────────────────────────────────────────────────────────────┤
│  Mira's skills  (SKILL.md packages — see §2.5)                  │
│   discover_source │ research_vendor │ profile_table │ draft_map │
│   render_irr │ generate_connector │ open_pr │ run_dry_sync │    │
│   run_initial_sync │ schedule_delta │ issue_dashboard_jwt │ ... │
├─────────────────────────────────────────────────────────────────┤
│  Decision engine (a meta-skill)                                 │
│   • picks next question / next skill                            │
│   • detects "enough info to proceed"                            │
│   • escalates to FDE on low confidence / blockers               │
├─────────────────────────────────────────────────────────────────┤
│  Onboarding State Object  (see §2.2 — single source of truth    │
│  for the run; persisted in Supabase Postgres; skills read/write)│
├─────────────────────────────────────────────────────────────────┤
│  State machine (enforced server-side in Supabase):              │
│  Intake → Research → Map → Approve → Code → DryRun →            │
│  InitialSync → Schedule                                         │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Onboarding State Object (canonical schema)

Persisted as a row in Supabase Postgres (`onboarding_runs`) and mutated by every agent step. The decision engine reads this object to choose the next question or transition.

```jsonc
{
  "run_id": "uuid",
  "company_id": "string",
  "state": "intake | research | map | awaiting_approval | code | dry_run | initial_sync | scheduled | failed",
  "source": {
    "system": "stripe | invoiced | google_sheets | epicor | generic_rest | csv_drop | sftp | unknown",
    "deployment": "cloud | on_prem | hybrid | unknown",
    "access_method": "api_key | oauth | db_dump | sftp | shared_drive | csv_export | unknown",
    "auth_status": "missing | provided | validated | failed",
    "frequency_required": "realtime | hourly | daily | weekly",
    "historical_backfill_required": true,
    "business_quirks": ["string"]
  },
  "tables_in_scope": ["invoice", "customer", "contact"],
  "artifacts_collected": [
    { "kind": "sample_csv | api_doc_url | uploaded_pdf | api_response_sample", "uri": "string", "ingested_at": "ISO8601" }
  ],
  "table_descriptions": [ /* see §3.3 */ ],
  "column_descriptions": [ /* see §3.3 */ ],
  "mapping_contract": { /* see §4.2 — null until Phase 2.5 produces it */ },
  "approval": {
    "customer_confirmed_at": null,
    "fde_confirmed_at": null,
    "fde_user": null
  },
  "blockers": [ { "code": "string", "message": "string", "needs": "customer_input | fde_input | research" } ],
  "next_question": "string|null",
  "confidence_overall": 0.0
}
```

### 2.3 Tech stack (must align with `0001-prd.md`)

| Component | Choice |
| :--- | :--- |
| **Agent runtime** | **LangGraph** (Custom built). We are *not* installing the OpenClaw binary. Instead, we are building a LangGraph state machine that *mimics the essence* of OpenClaw's architecture: bootstrap-file personas, a strict skills system, JSONL sessions, and Telegram channel bindings. |
| **Chat surface** | **Telegram** (Custom Bot Integration). One Telegram group per onboarding run. Mention-gated activation, allowlist policy enforced by our bot logic. |
| **Skill format** | **AgentSkills-inspired `SKILL.md`** with YAML frontmatter (see §2.5 for the catalog). Skills are version-controlled in this repo under `agent/skills/` and loaded as LangGraph tools. |
| **Orchestrator (workflows)** | **Airflow** for scheduled delta syncs; dry-run + initial sync execute as skills inside Mira's per-run sandbox on Nebius compute. |
| **Control plane DB** | **Supabase Postgres** — `onboarding_runs`, `connector_configs`, `mapping_versions`, `run_history`, `validation_results`. The session JSONL is the *conversational* log; Supabase is the *structured-state* log. |
| **Mid-layer CSV storage** | **Supabase Storage** bucket `midlayer-csv` (per `0002`). |
| **Object storage (raw + replay)** | **Nebius Object Storage**. |
| **Analytics / observability** | **ClickHouse** (run metrics, anomaly detection, freshness). |
| **Code repository** | The mono-repo this PRD lives in. PRs opened via GitHub API by the `open_pr` skill. |
| **Telemetry** | **OpenTelemetry** → ClickHouse. LangGraph node/tool invocations are wrapped with OTel spans. |
| **Notifications** | In-Telegram-group pings (`@FDE`) for blockers; Slack mirror for FDE-side ops. |

**Why OpenClaw-inspired:** The transcript explicitly dismissed using the OpenClaw framework directly as "too generalized / enthusiast-focused" for an enterprise ERP ingestion product. We agree: **we will not install the OpenClaw binary.** However, its *architectural essence*—a stateful agent loop, persona via bootstrap files, a clean skills extension model, and per-group session isolation—is exactly the UX we want. We will build these primitives into our custom LangGraph orchestrator, constraining it to behave as an enterprise ERP onboarding specialist.

### 2.4 OpenClaw-inspired concept mapping

| Our concept | Implementation in our LangGraph stack | Notes |
| :--- | :--- | :--- |
| Mira (the AI Forward Engineer) | A LangGraph agent configured via bootstrap files | All bootstrap files + skill allowlist live under this agent. |
| Per-customer onboarding run | A persisted session transcript (JSONL) | Session JSONL persisted to Object Storage/Supabase. |
| Telegram group | Custom Telegram bot webhook | `groupPolicy: allowlist`, `requireMention: true` for read-only members; `/approve-*` slash commands restricted to the customer + FDE jids. |
| Conversation transcript | Session JSONL | Source of truth for replay, debugging, and audit of what Mira said and why. |
| Structured run state | Supabase `onboarding_runs` row keyed by `run_id` | The session JSONL is the *narrative*; this row is the *contract* (see §2.2). Skills mutate it via the `state_store` tool. |
| Mira's capabilities | Skills (LangGraph Tools) | One skill per discrete capability — see §2.5. |
| Mira's persona + rules | `IDENTITY.md`, `SOUL.md`, `AGENTS.md`, `USER.md`, `TOOLS.md`, `BOOTSTRAP.md` | See §2.6. |
| Per-run isolation | Ephemeral Docker container / Nebius compute instance | Each onboarding run gets its own workspace. Generated connector code is written + executed there before being pushed to GitHub. |
| Approvals | Telegram slash commands `/approve_customer`, `/approve_fde` | Each approval writes a timestamp to `onboarding_runs.approval.*` and is signed with the Telegram user id. |
| Steering mid-run | LangGraph interrupt / human-in-the-loop node | Customer can interject ("wait, that's not the right table") and Mira ingests it at the next model boundary without losing in-flight tool calls. |

### 2.5 Mira's skill catalog (initial)

Each skill is a folder under `agent/skills/<skill_id>/` containing `SKILL.md` (YAML frontmatter + instructions) plus any helper scripts. Skills are loaded as LangGraph tools. The agent's prompt restricts Mira to exactly this catalog so she cannot drift into off-purpose behavior.

| Skill id | Phase | What it does |
| :--- | :--- | :--- |
| `discover_source` | 2 | Runs the §3.2 intake conversation. Reads/writes `source.*` on the state object. Knows which question to ask next. |
| `validate_credentials` | 2 | Accepts an API key / OAuth flow / file drop. Probes the source. Sets `auth_status`. Stores secrets in Supabase Vault by reference only. |
| `research_vendor` | 2 | Fetches vendor docs, API specs, and known-quirks knowledge base. Writes findings into `artifacts_collected`. Gated by `requires.bins: ["uv"]` and `requires.env: ["TAVILY_API_KEY"]`. |
| `profile_table` | 2 | For one table: produces the §3.3 Table description + every Column description by inspecting samples + docs. |
| `draft_mapping` | 2.5 | Generates the per-field mapping with confidences + transforms for the merge.dev mid-layer schema. Writes `mapping_contract` (draft). |
| `render_irr` | 2.5 | Renders the §4.3 Implementation Readiness Review and posts it to the Telegram group. |
| `await_approvals` | 2.5 | Listens for `/approve_customer` and `/approve_fde` slash commands. Validates senders. Writes timestamps. Refuses to advance the state machine until both land. |
| `lock_contract` | 3.1 | Step 1 of §5.2. Freezes `mapping_version` + `midlayer_schema_version` in Supabase. |
| `generate_connector` | 3.2 | Step 2 of §5.2. Fills the §5.3 connector-package templates. Writes files to the sandbox workspace. |
| `generate_tests` | 3.3 | Step 3 of §5.2. Generates fixture + transform + delta-cursor tests. |
| `open_pr` | 3.4 | Step 4 of §5.2. Creates branch, commits, opens GitHub PR via the GitHub API, with the IRR pasted in the PR body. |
| `run_dry_sync` | 3.5 | Step 5 of §5.2. Executes the generated connector inside the sandbox on ≤100 sample rows. Posts validation summary in-group. |
| `run_initial_sync` | 3.6 | Step 6 of §5.2. Full historical backfill → CSVs to Supabase per `0002` naming. |
| `schedule_delta_sync` | 3.7 | Step 7 of §5.2. Generates and commits Airflow DAG; registers cursor state. |
| `issue_dashboard_jwt` | 3 | Mints a JWT scoped to `(company_id, run_id)`, posts the magic-login URL into the group. |
| `state_store` | (cross-cutting) | The single read/write skill for the `onboarding_runs` row. All other skills MUST go through this skill — never write to Supabase directly — so every state mutation is logged and replayable. |
| `escalate_to_fde` | (cross-cutting) | Posts an `@FDE` mention in-group with a structured blocker payload. |

Skills are **the only way** Mira does work. The system prompt (via `AGENTS.md`) explicitly forbids ad-hoc tool use outside this catalog. New capabilities are added by writing a new skill, not by patching prompts.

### 2.6 Bootstrap files (Mira's persona + rules)

These files are version-controlled in this repo at `agent/mira/`. The LangGraph entry node injects them into the system prompt on the first turn of every new session.

| File | Purpose | Owner |
| :--- | :--- | :--- |
| `IDENTITY.md` | Mira's name, vibe, emoji. Short. | Product |
| `SOUL.md` | Persona, boundaries, tone: "calm, procedural, proactive, specific, never vague, always says what she needs next and why." Forbids freeform chit-chat, opinionated commentary, or off-purpose help. | Product |
| `AGENTS.md` | Operating instructions: the state machine, the rule that all work goes through skills, the two-action approval gate, the structured-verbosity contract for Phase 3, escalation rules. | Engineering |
| `USER.md` | Per-run profile of who Mira is talking to: customer name, company, role; FDE name + Telegram jid; preferred address. Generated by the FDE-side onboarding tool when the Telegram group is created. | FDE tooling |
| `TOOLS.md` | Notes on how Mira should use her skills (e.g., "always call `validate_credentials` immediately after the user pastes anything that looks like a key — never echo the key back"). | Engineering |
| `BOOTSTRAP.md` | One-time first-turn ritual: introduce yourself, ask the §3.2 step-1 questions, read `USER.md` to address the customer by name. Deleted after first run completes. | Engineering |

### 2.7 Session, workspace, and sandbox per run

- **Session.** Each onboarding run is one session. Session id == our `run_id`. Transcript lives in Supabase or Object Storage as a JSONL. We back this folder up to Nebius Object Storage nightly for audit.
- **Workspace.** Each run gets its own sandboxed workspace. Generated connector code is written there. The `open_pr` skill reads from this workspace and pushes to GitHub.
- **Sandbox.** An ephemeral Docker sandbox on Nebius is used for any code execution: `run_dry_sync` and `run_initial_sync` execute the generated Python connector inside this sandbox so a misbehaving connector can never touch the host or another customer's data.
- **Group/session binding.** If the same Telegram group is reused for a re-run (e.g., after a mapping correction), it gets a *new* session id (== new `run_id`) — sessions are one-to-one with runs, not with groups, to preserve the immutability rule (§5.6).

---

## 3. Phase 2 — Discovery & Source Understanding

**Goal:** From a cold start, produce a structured profile of the source system and the in-scope tables that is rich enough for Phase 2.5 to draft a mapping.

### 3.1 Inputs (any combination)

Mira accepts any of the following at any point in the conversation:

- **API access**: API key, endpoint, OAuth client config.
- **File uploads**: dataset preview (CSV / JSON / Excel), business documentation (PDF, memo, manual), schema dumps.
- **URLs**: vendor docs, API reference, public schema page, support thread.
- **Free-form user guidance**: business definitions ("our `customer_id` actually maps to the parent org, not the billing contact").

### 3.2 Core flow

1. **Guided intake conversation.** Mira proactively asks the minimum required to populate `source.*` and `tables_in_scope` in the state object. Never asks a question already answered. Examples: "Which ERP are you using?", "Is it cloud or on-prem?", "Which objects matter first — invoices, customers, contacts?", "What access do you have — API, DB dump, file export?".
2. **Credential gathering.** When `access_method` requires secrets, Mira links the user to a secure credential drop (Supabase Vault / Nebius Secrets), validates them, and sets `auth_status = validated`. If on-prem, Mira generates a step-by-step export guide instead.
3. **Autonomous research.** The Research Engine ingests vendor docs, API specs, MCP-exposed source servers, sample data, and prior knowledge of the source system to derive entity shapes and known gotchas.
4. **Collection-path proposal.** Mira recommends one of: direct API pull, recurring file drop, DB dump, SFTP, or mixed mode — with reasoning. Records to `source.access_method`.
5. **Per-table & per-column profiling.** Mira produces the structured artifacts in §3.3 for every table in scope.

### 3.3 Phase 2 output artifacts (schemas)

Both artifacts are JSON, persisted on the state object and rendered as markdown for human review.

**Table description (per table)**
```jsonc
{
  "table_name": "invoice",
  "summary": "Represents a billable invoice issued to a customer; one row per invoice",
  "row_grain": "one invoice (header). Line items live in a separate table.",
  "linkages": [
    { "to_table": "customer", "via": "customer_id", "cardinality": "many_to_one" }
  ],
  "datasource": "Stripe REST API /v1/invoices",
  "pull_process": "Paginated GET with starting_after cursor; updated_after for delta",
  "known_quirks": ["amounts in cents", "id has 'in_' prefix"]
}
```

**Column description (per column)**
```jsonc
{
  "table_name": "invoice",
  "field": "amount_due",
  "datatype": "integer",
  "domain": { "kind": "range", "min": 0, "max": null },
  "missing_indicator": "0 or null",
  "unit": "currency_minor_units (cents)",
  "semantic_role": "monetary_amount",
  "nl_summary": "Total amount the customer still owes for this invoice, in the smallest currency unit (cents for USD)."
}
```

`domain.kind` ∈ `categorical | range | regex | unique_id | freeform_text`.
`semantic_role` ∈ `monetary_amount | currency_code | timestamp | identifier | foreign_key | category | text | boolean | other`.

### 3.4 Exit criteria for Phase 2

- `source.system`, `source.access_method`, `source.auth_status = validated` are all set.
- For every table in `tables_in_scope`: a Table description + a Column description for every column observed in samples or docs.
- `confidence_overall >= 0.7` OR Mira has logged a blocker explaining what is missing.

---

## 4. Phase 2.5 — The Handshake (Mapping Negotiation)

**Goal:** Produce a frozen, human-approved **mapping contract** that deterministically dictates Phase 3.

### 4.1 Core flow

1. **Draft mapping.** Mira generates a per-field mapping from each external table to the merge.dev-aligned mid-layer schema (`schemas/midlayer/v1/{invoice,customer,contact}.schema.json` from `0002`).
2. **Score & annotate.** Every mapped field gets a confidence score and an explicit transform list.
3. **Fallback handling.** Any source field Mira cannot map confidently is routed to the `_unmapped` JSON column (per `0002` §2) — never dropped silently.
4. **Implementation Readiness Review.** Mira produces a structured markdown document (see §4.3) and presents it to the customer + FDE.
5. **Two-action approval gate.** Both approvals must land before Phase 3 begins:
   - **Customer** confirms business meaning is correct.
   - **FDE** confirms the implementation plan is sound.
   On approval, the mapping contract is **frozen** with a `mapping_version` (semver-ish: `stripe.invoice.v1.0.0`) and stored immutably in Supabase Postgres.

### 4.2 Mapping contract schema (the single Phase 3 input)

```jsonc
{
  "mapping_version": "stripe.invoice.v1.0.0",
  "midlayer_schema_version": "v1",
  "company_id": "acme",
  "source_profile": { /* from §2.2 source.* */ },
  "objects": [
    {
      "midlayer_table": "invoice",
      "source_entity": "stripe.invoice",
      "fields": [
        {
          "midlayer_field": "amount_due",
          "source_field": "amount_due",
          "confidence": 0.98,
          "transforms": [
            { "op": "divide", "by": 100, "reason": "Stripe stores cents, mid-layer stores major units" },
            { "op": "cast", "to": "decimal(18,4)" }
          ],
          "notes": "Stripe always returns integer cents; safe to divide."
        },
        {
          "midlayer_field": "currency",
          "source_field": "currency",
          "confidence": 0.99,
          "transforms": [{ "op": "uppercase" }, { "op": "validate_iso_4217" }]
        },
        {
          "midlayer_field": "issue_date",
          "source_field": "created",
          "confidence": 0.95,
          "transforms": [{ "op": "epoch_to_iso8601_utc" }]
        }
      ],
      "unmapped_source_fields": ["statement_descriptor", "footer"],
      "object_confidence": 0.97
    }
  ],
  "sync_strategy": {
    "initial": "full_historical",
    "delta": { "mode": "cursor", "cursor_field": "updated", "cadence": "daily" }
  },
  "validation_requirements": [
    "row_count_matches_source",
    "no_null_in_required_fields",
    "currency_present_when_amount_present",
    "stripe_specific:cents_to_dollars_sanity_check"
  ]
}
```

### 4.3 Implementation Readiness Review (markdown rendered for humans)

```
Implementation Readiness Review — <company_id> — <source_system>

Source identified: Stripe (cloud, REST API)
Access validated: API key (live mode, restricted to read)
Objects in scope:
  - invoices  (object_confidence 0.97 — high)
  - customers (object_confidence 0.94 — high)
  - contacts  (object_confidence 0.71 — medium — see notes)

Planned sync behavior:
  - initial backfill: full historical (~ 850k invoices estimated)
  - delta sync: daily by `updated` timestamp, cursor-based

Known transforms:
  - amount fields: cents → dollars (÷100), cast to decimal(18,4)
  - timestamps: epoch → ISO 8601 UTC
  - invoice id: preserve raw `in_…` prefix; populate normalized `external_id`
  - currency: uppercase, validate ISO-4217

Fallback handling:
  - 7 unmapped fields will land in `_unmapped` JSON column

Code to be generated (preview): see §5.3 layout

Approval required:
  [ ] Customer confirms business meaning
  [ ] FDE confirms implementation plan
```

### 4.4 Exit criteria for Phase 2.5

- A complete `mapping_contract` JSON exists, validated against its own schema.
- `approval.customer_confirmed_at` AND `approval.fde_confirmed_at` are both non-null.
- `mapping_version` is committed to `mapping_versions` table (immutable).

---

## 5. Phase 3 — Implementation & Execution

**Goal:** Deterministically turn the approved mapping contract into runnable connector code, run it, and give everyone observable artifacts.

### 5.1 Operating principle: structured verbosity

Mira exposes progress as **discrete, ordered steps with tangible artifacts**, not a stream of consciousness. Every step posts a chat message containing: step name, inputs consumed, outputs produced, links.

### 5.2 The seven Phase 3 steps

| # | Step | Tangible artifact |
| :-- | :--- | :--- |
| 1 | **Lock implementation contract** | Freeze `mapping_version` + `midlayer_schema_version` + sync strategy in Postgres |
| 2 | **Generate connector code** | Files in `connectors/<company_id>/<source>/` (see §5.3) |
| 3 | **Generate tests** | Fixture tests, schema validation tests, transform unit tests, delta-cursor tests |
| 4 | **Open PR** | Branch `connector/<company_id>/<source>/<mapping_version>` + GitHub PR link with diff and the IRR markdown in the PR body |
| 5 | **Dry run** | Pull a small sample (≤100 rows per table), transform, write preview CSV + validation summary to a non-prod Supabase prefix |
| 6 | **Initial sync** | Full historical backfill → CSVs at `midlayer-csv/<company_id>/<table>/initial/...` per `0002` naming convention |
| 7 | **Schedule delta sync** | Generated Airflow DAG committed to repo; first scheduled run registered with cursor state |

### 5.3 Connector package layout (template-constrained)

Per-source generated code lives under `connectors/`:

```
connectors/<company_id>/<source_name>/
  connector_config.yaml      # source profile, auth ref, tables, mapping_version pointer
  source_adapter.py          # implements DataConnector interface — raw record extraction
  transform_invoice.py       # applies mapping_contract.objects[invoice] transforms
  transform_customer.py
  transform_contact.py
  sync_runner.py             # entrypoint — wires adapter + transforms + writer + validator
  validation.py              # company/source-specific assertions on top of generic ones
  tests/
    fixtures/                # 3+ sample raw records per table
    test_transforms.py
    test_schema_compliance.py
    test_delta_cursor.py
  README.md                  # auto-generated — describes source, mapping_version, run cmds
```

Shared framework code lives under `framework/` (written once, reused across all connectors — Mira does **not** regenerate this):

```
framework/
  connector_interface.py     # DataConnector ABC: extract_initial(), extract_delta(cursor)
  csv_writer.py              # enforces 0002 CSV format spec
  scheduling.py              # Airflow DAG factory
  secrets.py                 # Supabase Vault / Nebius Secrets accessors
  observability.py           # OpenTelemetry hooks → ClickHouse
  midlayer_models.py         # Pydantic models from schemas/midlayer/v1/
  mapping_engine.py          # generic applier of mapping_contract transforms
```

**Why template-constrained:** keeps PRs reviewable, avoids one-off code, makes upgrades safe. Mira fills in templates; it does not invent architecture.

### 5.4 The three Phase 3 outputs

Every Phase 3 run must produce all three. Missing any one is a failure.

| Output | Contents | Where |
| :--- | :--- | :--- |
| **Code artifact** | Connector package + tests + Airflow DAG | GitHub PR |
| **Data artifact** | Initial CSV(s), preview CSV, manifest, dropped-columns report, transform summary | Supabase `midlayer-csv` bucket per `0002` layout |
| **Review artifact** | Mapping contract markdown, IRR, run logs, row counts, validation summary, links to PR + CSVs | JWT-gated dashboard (§5.5) |

### 5.5 Observability dashboard

- **Access:** Magic JWT auto-login link dropped directly into the chat, scoped to `(company_id, run_id)`. Allows the FDE and customer to check progress at any time without a separate login step.
- **Contents:**
  - Status of all 7 Phase 3 steps (and current state from §2.2).
  - Link to PR + code diff.
  - The frozen mapping contract (JSON + rendered markdown).
  - Links to every generated CSV in `midlayer-csv` (initial + each delta date).
  - Run logs (rows in / rows out / dropped columns / API errors).
  - Validation summary per run (which assertions from §4.2 passed/failed).
- **Backed by:** Supabase Postgres (run history) + ClickHouse (metrics, freshness, anomalies).

### 5.6 Immutability & re-runs

- Re-runs and corrections produce **new pipeline runs and new CSV artifacts** with new `run_id`s. Historical CSVs are never overwritten (matches `0001-prd.md` §3 and `0002` §3).
- A correction loop is: edit mapping → produces a new `mapping_version` → goes back through the §4 approval gate → triggers a new Phase 3 run.

---

## 6. Cross-cutting Guardrails

1. **State machine is enforced.** Transitions are validated server-side in Supabase against the table in §6.1 (e.g., cannot enter `code` state without both approval timestamps). Illegal transitions raise and `escalate_to_fde` fires.
2. **Skill discipline.** Mira's only path to action is invoking a skill from the §2.5 catalog. `AGENTS.md` forbids ad-hoc shell or HTTP calls outside skills. New capabilities require a new skill, not prompt patches.
3. **Template constraint.** Codegen targets the templates in §5.3 only. The `generate_connector` skill rejects free-form output that doesn't match the template AST.
4. **No data loss.** Any source field not in the mapping must land in `_unmapped` (per `0002` §2). Validation rejects rows that violate this.
5. **Auditability.** Every chat turn (Session JSONL), every state mutation (Supabase `onboarding_runs` history table), every research lookup, and every codegen step is logged with `run_id` for replay.
6. **Confidence-driven escalation.** Any field with `confidence < 0.6` or any `object_confidence < 0.8` is flagged in the IRR and requires explicit FDE acknowledgment via `/approve_fde`.
7. **Secrets handling.** Credentials are never written to the repo, never logged in the session JSONL (the `validate_credentials` skill redacts before tool I/O is recorded), never echoed in chat. Stored in Supabase Vault; referenced by ID only in `connector_config.yaml`.
8. **Sandbox isolation.** All generated-connector execution happens inside the per-run ephemeral sandbox. The sandbox has no access to other runs' workspaces, the host filesystem, or production credentials.

### 6.1 Legal state transitions

| From → To | Required precondition |
| :--- | :--- |
| `intake → research` | `source.system != unknown` |
| `research → map` | exit criteria of §3.4 met |
| `map → awaiting_approval` | `mapping_contract` validates against its schema |
| `awaiting_approval → code` | `approval.customer_confirmed_at` AND `approval.fde_confirmed_at` both non-null |
| `code → dry_run` | `open_pr` skill returned a PR URL |
| `dry_run → initial_sync` | dry-run validation summary has zero `error`-severity findings |
| `initial_sync → scheduled` | initial-sync manifest emitted per `0002` §5 |
| any → `failed` | unrecoverable error; `escalate_to_fde` must fire |

---

## 7. MVP Scope & Acceptance Criteria

### 7.1 In-scope sources for MVP
- **Stripe** (primary test case — exercises cents→dollars, prefixed IDs, epoch timestamps, pagination).
- **Google Sheets** (exercises messy header rows, manual export).
- **Invoiced.com** (per `docs/sources/invoiced-data-format.md` — exercises generic REST + nested-JSON-into-flat-column convention).

### 7.2 In-scope tables
`invoice`, `customer`, `contact` (per `0001-prd.md` §6).

### 7.3 Definition of Done (Phase 2 / 2.5 / 3)

**Agent runtime setup (OpenClaw-inspired)**
- [ ] LangGraph agent runtime deployed; implements the OpenClaw-style bootstrap file injection and skill routing.
- [ ] Mira's bootstrap files (`AGENTS.md`, `IDENTITY.md`, `SOUL.md`, `USER.md`, `TOOLS.md`, `BOOTSTRAP.md`) committed under `agent/mira/` and injected into the system prompt.
- [ ] All §2.5 skills implemented as LangGraph tools under `agent/skills/<skill_id>/`.
- [ ] Telegram channel binding configured with `groupPolicy: allowlist`, `requireMention: true`, owner-only `/approve-*` slash commands, and per-session sandboxing enabled.
- [ ] Per-run sandbox `setupCommand` pre-installs `uv`, `python3.12`, and the `framework/` package; verified by a smoke test running `run_dry_sync` end-to-end.

**State machine + state object**
- [ ] State machine enforced server-side in Supabase (Postgres triggers or row-level checks) with all states in §2.2 and the legal-transition table from §6.1.
- [ ] Onboarding State Object schema published as Pydantic model + JSON Schema; the `state_store` skill is the only writer.

**End-to-end behavior**
- [ ] Mira can complete a full Stripe onboarding from cold start (FDE creates a new Telegram group + customer joins) to scheduled delta sync, with **zero** human input outside the two approval slash-commands.
- [ ] Phase 2 produces compliant Table + Column descriptions for all three MVP tables on Stripe and Invoiced.com.
- [ ] Phase 2.5 produces a valid `mapping_contract` JSON that passes its own schema validation; IRR markdown rendered correctly.
- [ ] Two-action approval gate enforced (state machine refuses to enter `code` without both timestamps).
- [ ] Phase 3 generates a connector package matching §5.3 layout for Stripe; PR opens automatically with IRR in body.
- [ ] Dry run produces a preview CSV that passes all `0002` validation gates on the seed fixtures (golden outputs match).
- [ ] Initial sync writes CSVs to Supabase `midlayer-csv` bucket using `0002` naming + format spec.
- [ ] Airflow DAG for daily delta sync is generated, committed, and successfully runs once.
- [ ] JWT-gated dashboard renders all artifacts in §5.5 for the run.
- [ ] Re-running a corrected mapping produces a new `mapping_version`, a new Phase 3 run (new session id), and new CSVs without mutating prior outputs.
- [ ] Session JSONL transcripts archived nightly to Nebius Object Storage; replay tooling can reconstruct any past run from `(run_id, session_jsonl, onboarding_runs row)`.

### 7.4 Out of scope (deferred)
- Phase 4 (mid-layer → target DB sync) — see `0001-prd.md`.
- Phase 5 (advanced validation & self-improvement loops).
- IDE plugin (JetBrains) — chat UI only for MVP.
- Sources beyond Stripe / Google Sheets / Invoiced.com.

---

## 8. Open Questions (track in follow-up specs)

1. **Mapping versioning scheme** — semver vs content-hash; impact on dashboard history.
2. **PR auto-merge policy** — does FDE approval on the IRR also auto-approve the GitHub PR, or is GitHub review a third gate?
3. **Sample-row privacy** — when Mira ingests sample data, what redaction happens before logs/artifacts are written? (interacts with Session JSONL — those logs contain raw tool I/O).
4. **Multi-source onboarding** — can one onboarding run cover Stripe + Google Sheets simultaneously, or must they be separate runs (and therefore separate Telegram groups + sessions)?
5. **Knowledge base for the Research Engine** — Gary Tang / G-Stack vs simpler RAG over vendor docs; deferred until a second source onboarding stresses recall quality.
6. **Model backend** — which model drives Mira: a Claude-class model or a self-hosted model on Nebius? Affects cost, latency, and skill prompt budget.
7. **Multi-FDE coverage** — can multiple FDEs be added to one Telegram group, and does either of them satisfy `/approve_fde`, or do we require a specific FDE assigned at group creation?
8. **Skill upgrade rollout** — when we ship a new version of e.g. `generate_connector`, do in-flight runs pick up the new skill mid-session (hot-reloading) or do we pin a skill snapshot per `run_id` for reproducibility? Recommended default: pin per run.
