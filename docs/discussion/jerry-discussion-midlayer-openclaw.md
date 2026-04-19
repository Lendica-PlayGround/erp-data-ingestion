build a prd to create a openclaw style agent that does phese 2-phase 3 (reference ) and run the code to create the midlayer data



help me discuss all features/idea i m thinking. so i can build a disstil a prd after the conversation. background i wnat to build AI forward engineer and particularlly this part phase 2, 2.5, and 3 I m think about experience that is like openclaw refrence: ## Product Requirements Document: Agentic ERP Data Ingestion System **Date:** April 18, 2026 **Topic:** Auto-forward engineering legacy ERP to mid-layer, and mid-layer to target DB --- ### 1. Executive Summary The primary objective is to build an "Agentic Deployment Engineer." This system will completely automate the end-to-end flow of migrating and syncing data from any legacy ERP system or data provider (e.g., Stripe, Epicor, Google Sheets) into a unified mid-layer, and subsequently into a target database or data lake. The system utilizes autonomous agents to research unfamiliar APIs, generate schema mappings, write extraction scripts, and set up continuous data pipelines with human-in-the-loop validation. ### 2. Target User Experience & Onboarding The onboarding process heavily utilizes a Test-Driven Development (TDD) approach driven by a natural language interface. 1. **Input:** The user (or onboarding agent) provides API credentials and a small sample set of data (e.g., 3 historical invoices) via a chat interface or IDE plugin. 2. **Exploration:** The AI agent autonomously searches the web, reads official documentation, MCP servers, and forums to understand the source system's quirks and constraints. 3. **Proposal:** The agent generates a configuration plan, schema mapping, and extraction script, outputting it in a readable format (Markdown/JSON). 4. **Validation:** The user reviews the plan and the sample output. The user can provide natural language feedback to correct anomalies. 5. **Execution:** Once approved, the system automatically commits the pipeline (e.g., an Airflow DAG) to the execution environment. 6. **Maintenance:** The system runs an initial heavy extraction, followed by daily scheduled delta syncs. ### 3. Core Architecture & Pipelines **Phase 1: Agentic Exploration & Mapping Layer** * **Data Explorer Agent:** Ingests documentation and API specs for unknown providers to figure out data structures. * **Mapping Engine:** Translates source data into a unified format (leveraging merge.dev for schema standardization). * **Format Resolution:** Automatically handles edge cases, such as finding the correct header rows in messy Google Sheets, or converting Stripe's cents-based integers into standard dollar-value floats. **Phase 2: Intermediate CSV Dump Layer** * **Initial Sync:** A heavy dump of historical data into a standardized CSV format. * **Delta Sync:** Daily scheduled jobs that only pull modified or updated data into new CSVs. * **Fallback Protocol:** Any unmapped columns are preserved under an "Other" category to prevent data loss. **Phase 3: Target Database Sync** * **Routing:** Moves the standardized intermediate CSVs into the final target database (dynamic or pre-defined). ### 4. Observability & Monitoring A robust monitoring system is required to ensure data integrity across the ingestion pipeline. * **Validation Checks:** Automated checks for missing rows, NaN values, incorrect formatting, and currency discrepancies. * **Alerting:** Real-time Slack notifications for pipeline failures or mapping anomalies. * **Actionable Logs:** Detailed daily logs of migrated rows and system actions, allowing the AI to self-improve or prompting the user for manual steering context. ### 5. Technical Stack | Component | Technology / Framework | | :--- | :--- | | **Orchestration / Pipeline** | Airflow (DAGs), Vercel Workflows | | **Agentic Framework** | LangGraph, Vercel Agents | | **Intermediate Storage** | Supabase (CSV storage) | | **Target Database / OLAP** | ClickHouse | | **Compute & Infrastructure** | Nebius AI | | **Knowledge Base / Retrieval** | Gary Tang / G-Stack (as proposed) | | **User Interface** | Natural Language Chat, JetBrains IDE Plugin | ### 6. MVP Scope & Constraints * **Supported Tables:** Customer, Invoices, Contacts. * **Scale Requirements:** Support for 100+ companies. * **Data Volume:** Up to 1,000,000 historical invoices per company, and 10,000 new invoices per day. * **Primary Test Case:** Stripe (specifically handling Stripe's CSV exports, cent-to-dollar conversions, and invoice naming conventions). --- **Note on "OpenClaw":** The transcript mentions "OpenClaw" (likely referring to the open-source agent framework OpenHands/OpenDevin). The team correctly identified that while it is powerful, it is too generalized and "enthusiast-focused" for an enterprise ERP ingestion product. Sticking to custom LangGraph or Vercel Agents integrated with Airflow is the recommended path forward for this specific scope. Implementation Plan Phase 1: Seed data + mid-layer uniform format (merge.dev-aligned) + CSV storage conventions Seed Data (Test-Driven Onboarding Input - Customer, Contact, Invoice) Provide one stripe account with seed data Provide one google sheet with seed data Bonus - data gets updated every minute Mid-Layer Uniform Schema (merge.dev-aligned) as a Markdown file Adopt merge.dev Accounting/CRM Common Models as the canonical schema for the three MVP tables: Invoice → merge.dev Accounting Invoice object Customer → merge.dev Accounting Contact (or Customer depending on category) object Contact → merge.dev CRM Contact object Publish schemas as versioned JSON Schema / Pydantic models in schemas/midlayer/v1/{invoice,customer,contact}.schema.json — single source of truth for validation. Monetary fields, Currency code, All timestamps Storage Target — CSV Layout on Supabase Bucket: midlayer-csv Folder structure File naming convention: <company_id>_<table>_<initial|delta>_<YYYYMMDD>[_<run_id>].csv CSV File Format Spec (strict, enforced) Output Google sheet, stripe secret, superbase secret a markdown file general mid layer guidance guidance {invoice,customer,contact}.schema.json Phase 2: Exploration Agent Input: User input similar to Openclaw. Users can start with any of the following: File upload for dataset preview: CSVs, JSONs, Provide an API key/endpoint/documentation Upload file for documentation, memos, and business manual exploration Url to explore User interaction and guidance Output: Structured Table description Table name Table Summary: A high-level description of what business process this table represents Linkages or relationships with other tables What each row represents Datasource: where the agent got the information about this What is the process for pulling this dataset Structured Table column info Field datatype eg string, int, char, etc Field Domain: range of values field can take: list of categories, range of numbers, text, regex field must match, etc. How missing data is indicated Unit of the field: if numerical is it a percent, currency, rating on scale, etc. Or if a field is a unique identifier, category, degree, text, etc. A natural language summary of what the field actually represents Phase 2.5: Handshake mapping Input: the data description from the exploration phase 2 Output: a JSON mapping the external dataset to the internal dataschema For each map also add a confidence score Also, additional dataprocessing may be needed. For example, convert datatypes and dataformats Ex cast ints to ints Change some category names to corresponding internal category Phase 3: A generic Python runner that, on a schedule: Reads a per-company connector config (any source — Stripe, Google Sheets, generic REST, etc.). Pulls raw records via a uniform DataConnector interface. Applies the Phase 2 mapping artifact to transform raw rows into the Phase 1 mid-layer schema (invoice / customer / contact). Writes a CSV that matches the Phase 1 layout/naming spec into the Supabase midlayer-csv bucket. Records run metadata + logs (rows in/out, dropped columns, errors) for the Phase 4 observability layer. Handles initial sync (full historical pull) and daily delta sync (cursor-based) per (company, table). Phase 4(Div):Mid to target DB source. - Nebius Object Storage is the canonical landing zone for raw files, transformed outputs, and replayable run artifacts. - Supabase Postgres is the control plane for connector configs, schema versions, mappings, run history, validation results, and object-storage pointers. - ClickHouse is the analytics and observability layer for run metrics, failures, anomaly tracking, freshness checks, and monitoring dashboards. - Ingestion scripts run on Nebius compute, transform source data into the canonical mid-layer schema, and write append-only outputs to the lake. - Phase 4 should prefer Parquet for stored lake files, with partitioning by company, table, sync type, date, and run ID. - Data must remain immutable per run: corrections happen through new runs rather than overwriting prior outputs. - Monitoring must cover both pipeline health and data quality, including failures, retries, stale syncs, row-count drift, null spikes, schema mismatches, and reconciliation issues. - Telemetry should flow through OpenTelemetry, with infra metrics from Nebius and analytical monitoring backed by ClickHouse. - MVP acceptance requires successful initial and delta syncs, metadata recorded per run, replayable failures, and Stripe-specific validation for invoice consistency and cents-to-dollars normalization Merge reference https://docs.merge.dev/merge-unified/accounting/common-models/contacts/list https://docs.merge.dev/merge-unified/accounting/common-models/invoices/list Phase 5 (Div): Validation And Testing



Thought for 8s

Yes — let’s turn this into a product-shaping discussion, not just a doc rewrite.

What you have already is strong. The biggest opportunity now is to make Phase 2, 2.5, and 3 feel like one coherent product experience instead of three technical modules.

Here is the cleanest way to think about it.



The product you are actually building

You are not just building “ERP ingestion.”

You are building an AI Forward Engineer for data systems:



it understands an unknown source

it proposes how that source maps into your canonical model

it operationalizes that proposal into a repeatable sync pipeline

So the product arc is:



Understand the source

Negotiate the mapping

Run the pipeline

Observe and repair over time

That means:



Phase 2 = understanding

Phase 2.5 = agreement / handshake

**Phase

So I am thinking of how are we going to build this, right? So my, what I want is like a cloud, open cloud experience. It's like a chatbot. Ideally, it's the client, the bot. Let's give it a very human but bot name. And then a forward HDR, which is a human loop, just to kind of monitor and support. The agent should be, AI agent should be very proactive, right? Like, ask a couple questions the user wants the user to answer, and then kind of guide through the user to answer everything. So, you know, a conversation can be like, hey, what kind of ERP are you using? Oh, okay, it's, for example, it's Stripe. Sure, thank you. But then, can you then, I will need, you know, then the agent obviously do the research and then say, hey, I will need this API key. And then ask the user to provide the API key. That will be one example. And another example can be, hey, the agent asks the user, what data are you using? And then it says, oh, I'm using, let's say, Apicore and on-premise. And then the agent should then provide like a very clear step-by-step guide, say, hey, user, please follow this so you can create like a data dump into like this particular, you know, like file system. And then once you are done, we can kind of start ingestion. And then meanwhile, kind of give the, that's probably part one, right? Like, basically, interact with the user, get all the information, and then kind of, that's one big part. Get all the information, I mean, does the background research and come up with a way, like, how can we possibly create these like standardized CSV. That's really, I think it's called basically phase two and phase 2.5.

Yes — that is the right cut.

What you’re describing is not “a data ingestion tool with chat.”

It is a guided AI onboarding operator for forward engineering data sources into your mid-layer.

And the core product for Phase 2 + 2.5 is:



a proactive agent that interviews the user, researches the source, asks for the minimum missing inputs, and produces a trustworthy mapping plan plus execution instructions.

That is the product.



The experience you’re aiming for

The UX should feel like:



a named AI implementation specialist

paired with a human forward-deployment engineer

where the AI leads, and the human only steps in when confidence is low, setup is weird, or the customer is stuck

So the user should feel:



“I am being guided”

“the system knows what it still needs”

“I don’t need to understand the full pipeline”

“when something is ambiguous, someone catches it”

That is much better than a passive “upload docs and wait” experience.

Product framing

I would define the product loop like this:



1. Intake conversation

The agent asks targeted questions:



what system are you using

cloud or on-prem

what data objects matter first

what access method is available

API, DB dump, CSV export, SFTP, shared drive, etc.

frequency needed

historical backfill needed

any business quirks or field definitions

2. Source understanding

The agent researches:



vendor docs

API docs

export formats

auth requirements

common gotchas

likely tables / endpoints

how invoice, customer, contact data are represented

3. Collection path proposal

The agent proposes one of several paths:



direct API pull

guided manual export

recurring file drop

database dump

spreadsheet ingestion

mixed mode

4. Handshake mapping

The agent shows:



what source entities correspond to your canonical objects

what fields map cleanly

what fields need transforms

what fields are uncertain

what fields will fall into “Other”

5. Approval + execution handoff

After user confirmation:



generate mapping artifact

generate connector config

generate extraction instructions or runnable job config

queue initial sync

That is the complete Phase 2 / 2.5 product.

The key insight

You should build this as a stateful guided workflow wrapped in chat, not as a freeform chatbot.

The chat is only the surface.

Underneath, the system needs a clear state machine.

Because otherwise:



the agent will ask random repetitive questions

it won’t know what is missing

it won’t know when it has enough to proceed

users won’t trust it

So the architecture should be:



Conversational shell

Natural language UI



Structured onboarding state

A hidden object tracking:



source system

deployment type

access method

auth status

source artifacts collected

tables in scope

mapping completeness

confidence level

blockers

next question

Research engine

Looks up docs, examples, schemas, sample files



Decision engine

Determines:



what question to ask next

whether enough info exists to propose a mapping

whether to escalate to human

whether to generate instructions vs API connector flow

That will make it feel intelligent and proactive.

Recommended persona model

You mentioned a very human but bot-like name. That is a good idea.

I would make the product have two roles:



1. AI agent

Example role:



implementation specialist

onboarding engineer

data migration guide

Personality:



calm

procedural

proactive

specific

never vague

always says what it needs next and why

Good names are short and human-adjacent. Examples:



Mira

Rowan

Tess

Ava

Elio

June

Kai

Example:



“Hi, I’m Mira. I’ll help set up your source ingestion. I’ll ask a few questions, inspect your source materials, and propose a mapping before anything runs.”

That framing matters a lot.



2. Human support role

The “forward HDR” or deployment engineer should be visible, but secondary.

The user should understand:



AI handles 80–90%

human is monitoring quality and can step in

This

Now, this is great. And then afterwards, now let's also talk about like phase three, right? And then the agent should then just be able to kind of, with all the output, kind of confirm, hey, you know, the human for engineer, hey, I need you just to confirm all the data mapping, you know, the asks, requests to the user. And then if you are okay, like I am going to provide a start writing the code, right? And then after the human agrees, the foreign engineer, human for engineer agrees, then the agent should start to gather all of these like, you know, whatever output from 2.5 and read from like phase one all these like standardized CSV, how they should look like, and then what's like, you know, the initial set and then also the Delta updates, and then kind of create the cron job that needs to run to really grab whatever information from the user. Again, use Stripe as an example, like use an API key to do the mini data dump and then create it in the code base. And the data objects say we store in Superbase. So basically, the agent should do what phase three does is creating these jobs as code and add to the code base, probably create a pull request, right? Like commit and then create a pull request. And then basically then run the job such that in Superbase, we can see what kind of this meet layer data dump from the agent. And then the agent obviously should also be very, I mean, relatively verbose, right? Like every step it's doing, like kind of tell the group like what it plans to do and here's every step what it's doing. And also like show certain links to people on, hey, here are where we are and here's the intermediate results, both as in kind of code, the contract markdown, as well as like the mid layer like files, right? You can provide like links and probably create a dashboard with like a JWT token so that people can both one click, like look into it, but also have transparency every step along the way.

Yes — and this is where the product becomes really compelling.

Phase 3 is not just “run the pipeline.”

It is the moment where the AI stops being an analyst and becomes an implementation engineer.

So the clean product behavior is:



after the mapping is approved, the agent turns the approved contract into runnable ingestion code, opens a PR, runs the sync, and gives everyone visibility into what happened.

That is a very strong product story.



The end-to-end role split

I would define the roles like this:



Phase 2

The agent is a discovery + schema understanding assistant



Phase 2.5

The agent is a mapping negotiator



Phase 3

The agent is an execution engineer

And the human forward engineer is the approver / safety rail, not the main operator.

That matters a lot.

You do not want the human doing the work.

You want the human approving the AI’s work.

What Phase 3 should feel like in product terms

The experience should be:



Agent says: “I have enough to implement.”

Agent presents a final implementation plan.

Human forward engineer reviews and approves.

Agent writes the code.

Agent commits changes on a branch.

Agent opens a PR.

Agent runs an initial sync in a controlled environment.

Agent shows artifacts:code diff

mapping contract

run logs

generated CSVs

row counts / validation results

Human and customer can inspect everything from a dashboard.

That is the correct flow.

The core product model for Phase 3

Phase 3 should have three outputs, not one:



1. Code artifact

What the agent writes into the codebase:



connector config

source adapter logic

transformation logic

sync scheduler config

validation checks

logging hooks

2. Data artifact

What the run produces:



initial CSV dump

delta CSV dump

manifest / metadata

dropped columns report

transform summary

validation summary

3. Review artifact

What humans inspect:



mapping contract markdown

generated PR

preview of transformed rows

run dashboard

links to outputs

This separation is important because otherwise the product becomes “AI wrote code, trust me,” which is too opaque.

The approval checkpoint

You described this well: before codegen, the human forward engineer should confirm.

I think that approval should be explicit and structured.

The agent should say something like:



Implementation readiness review

Source identified: Stripe

Access validated: API key provided

Objects in scope: invoices, customers, contacts

Mapping confidence:invoices: high

customers: high

contacts: medium

Planned sync behavior:initial backfill: full historical

delta sync: daily by updated timestamp

Known transforms:cents to dollars

timestamp normalization

invoice naming normalization

Fallback handling:unmapped fields stored in other

Code to be generated:stripe connector

invoice/customer/contact transforms

CSV writer to Supabase

schedule config

logging and validation checks

Then two approval actions:



Customer confirms business meaning

Forward engineer confirms implementation

That is much better than a loose “looks good?”

What exactly the agent should generate in Phase 3

The agent should not just “write a script.”

It should generate a connector package with a standard structure.

For example:



/connectors/{company_id}/{source_name}/

  connector_config.yaml

  source_adapter.py

  transform_invoice.py

  transform_customer.py

  transform_contact.py

  sync_runner.py

  validation.py

  tests/

  README.md



And then shared framework code elsewhere:



/framework/

  connector_interface.py

  csv_writer.py

  scheduling.py

  secrets.py

  observability.py

  midlayer_models.py



This matters because the product should look like:



agent fills in a standard template

not agent invents one-off code every time

That will make the system far more reliable.

Recommended Phase 3 contract

The input to Phase 3 should be a single implementation bundle from earlier phases.

Something like:



Phase 3 input artifact

source profile

auth method

approved data objects

approved mapping JSON

transform rules

sync strategy

canonical schema version

company config

initial vs delta cursor strategy

destination config

validation requirements

So Phase 3 becomes deterministic:



given the approved onboarding contract, generate a runnable connector implementation.

That is a much better engineering boundary than “use chat context.”

The actual agent behavior in Phase 3

The agent should be verbose, but structured verbose.

Not a noisy stream of thought.

Better to expose progress as steps with artifacts.

For example:



Step 1 — Lock implementation contract

freezes mapping version

freezes schema version

records approved sync plan

Step 2 — Generate connector code

creates adapter for source

creates transforms for invoice/customer/contact

creates sync entrypoint

Step 3 — Generate tests

sample fixture tests

schema validation tests

transform correctness tests

delta cursor tests

Step 4 — Open PR

branch name

commit summary

pull request link

Step 5 — Run dry run

fetch small sample

transform records

write preview outputs

show validation summary

Step 6 — Run initial sync

backfill historical data

write outputs to Supabase / object storage

record run metadata

Step 7 — Schedule delta sync

create cron / Airflow DAG / workflow config

register cursor state handling

That level of verbosity is ideal.