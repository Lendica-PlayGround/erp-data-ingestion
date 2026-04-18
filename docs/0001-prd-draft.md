## Product Requirements Document: Agentic ERP Data Ingestion System

**Date:** April 18, 2026
**Topic:** Auto-forward engineering legacy ERP to mid-layer, and mid-layer to target DB

---

### 1. Executive Summary
The primary objective is to build an "Agentic Deployment Engineer." This system will completely automate the end-to-end flow of migrating and syncing data from any legacy ERP system or data provider (e.g., Stripe, Epicor, Google Sheets) into a unified mid-layer, and subsequently into a target database or data lake. The system utilizes autonomous agents to research unfamiliar APIs, generate schema mappings, write extraction scripts, and set up continuous data pipelines with human-in-the-loop validation.

### 2. Target User Experience & Onboarding
The onboarding process heavily utilizes a Test-Driven Development (TDD) approach driven by a natural language interface. 

1. **Input:** The user (or onboarding agent) provides API credentials and a small sample set of data (e.g., 3 historical invoices) via a chat interface or IDE plugin.
2. **Exploration:** The AI agent autonomously searches the web, reads official documentation, MCP servers, and forums to understand the source system's quirks and constraints.
3. **Proposal:** The agent generates a configuration plan, schema mapping, and extraction script, outputting it in a readable format (Markdown/JSON).
4. **Validation:** The user reviews the plan and the sample output. The user can provide natural language feedback to correct anomalies.
5. **Execution:** Once approved, the system automatically commits the pipeline (e.g., an Airflow DAG) to the execution environment.
6. **Maintenance:** The system runs an initial heavy extraction, followed by daily scheduled delta syncs.

### 3. Core Architecture & Pipelines

**Phase 1: Agentic Exploration & Mapping Layer**
* **Data Explorer Agent:** Ingests documentation and API specs for unknown providers to figure out data structures.
* **Mapping Engine:** Translates source data into a unified format (leveraging merge.dev for schema standardization).
* **Format Resolution:** Automatically handles edge cases, such as finding the correct header rows in messy Google Sheets, or converting Stripe's cents-based integers into standard dollar-value floats.

**Phase 2: Intermediate CSV Dump Layer**
* **Initial Sync:** A heavy dump of historical data into a standardized CSV format.
* **Delta Sync:** Daily scheduled jobs that only pull modified or updated data into new CSVs.
* **Fallback Protocol:** Any unmapped columns are preserved under an "Other" category to prevent data loss.

**Phase 3: Target Database Sync**
* **Routing:** Moves the standardized intermediate CSVs into the final target database (dynamic or pre-defined).

### 4. Observability & Monitoring
A robust monitoring system is required to ensure data integrity across the ingestion pipeline.

* **Validation Checks:** Automated checks for missing rows, NaN values, incorrect formatting, and currency discrepancies.
* **Alerting:** Real-time Slack notifications for pipeline failures or mapping anomalies.
* **Actionable Logs:** Detailed daily logs of migrated rows and system actions, allowing the AI to self-improve or prompting the user for manual steering context.

### 5. Technical Stack

| Component | Technology / Framework |
| :--- | :--- |
| **Orchestration / Pipeline** | Airflow (DAGs), Vercel Workflows |
| **Agentic Framework** | LangGraph, Vercel Agents |
| **Intermediate Storage** | Supabase (CSV storage) |
| **Target Database / OLAP** | ClickHouse |
| **Compute & Infrastructure** | Nebius AI |
| **Knowledge Base / Retrieval** | Gary Tang / G-Stack (as proposed) |
| **User Interface** | Natural Language Chat, JetBrains IDE Plugin |

### 6. MVP Scope & Constraints

* **Supported Tables:** Customer, Invoices, Contacts.
* **Scale Requirements:** Support for 100+ companies. 
* **Data Volume:** Up to 1,000,000 historical invoices per company, and 10,000 new invoices per day.
* **Primary Test Case:** Stripe (specifically handling Stripe's CSV exports, cent-to-dollar conversions, and invoice naming conventions). 

---

**Note on "OpenClaw":** The transcript mentions "OpenClaw" (likely referring to the open-source agent framework OpenHands/OpenDevin). The team correctly identified that while it is powerful, it is too generalized and "enthusiast-focused" for an enterprise ERP ingestion product. Sticking to custom LangGraph or Vercel Agents integrated with Airflow is the recommended path forward for this specific scope.