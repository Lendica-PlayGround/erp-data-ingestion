# Phase 2 Exploration Chatbot — Design Spec

**Date:** 2026-04-18
**Owner:** Phase 2 (`phase2/`)
**Status:** Approved for implementation
**Related:** [`phase2/phase2.prd`](../../phase2/phase2.prd), [`docs/0001-prd.md`](../0001-prd.md)

## 1. Purpose

Deliver the **Phase 2 Exploration Agent** from the PRD as a ChatGPT-style web app.
Users can explore an unfamiliar dataset / API / document by chatting with a single
OpenAI-backed agent; the agent produces structured table descriptions and
column-level metadata that feed Phase 2.5 handshake mapping.

## 2. User experience

Two-pane web UI:

- **Chat** (left): ChatGPT-like conversation with file upload, URL, and
  API-endpoint inputs. Assistant responses stream token-by-token.
- **Workspace** (right, tabbed):
  - *Files* — live view of `phase2/output/`; files changed in the last
    ~10 s are highlighted.
  - *Commits* — timeline of auto-commits the agent made.
  - *Uploads* — files the current session uploaded.

## 3. Inputs (per PRD)

- CSV / JSON / PDF / Markdown / text uploads (`POST /upload`).
- API key + endpoint + docs URL supplied as chat messages; the agent calls
  `fetch_url` / `call_api` tools.
- Free-text guidance from the user.

## 4. Outputs (per PRD)

For each table the agent identifies it writes two artifacts under
`phase2/output/tables/<slug>/`:

- `description.md` — Structured Table Description
  - Table name, summary, row meaning, relationships, datasource,
    retrieval process.
- `columns.json` — Structured Table Column Info
  - Array of `{name, datatype, domain, unit, description}` objects where
    `domain` is a tagged union (`categories | range | regex | text`) and
    `unit` is a tagged union (`currency | percent | scale | identifier |
    category | degree | text | count | datetime | none`).

A top-level `phase2/output/INDEX.md` links every table the agent has
described so the user can see progress at a glance.

## 5. Architecture

- `phase2/backend/` — FastAPI + LangGraph (single agent, multi-tool) +
  OpenAI.
- `phase2/frontend/` — Next.js 15 (App Router, TS, Tailwind, shadcn/ui).
- `phase2/output/` — artifact store, auto-committed to the outer git repo.

```
Browser ──► FastAPI ──► LangGraph agent ──► OpenAI
                          │
                          ├─► tools: read/write/list files,
                          │          preview_csv / preview_json,
                          │          fetch_url, call_api, git_commit
                          ▼
                phase2/output/  ──► git commit (scoped)
                          │
                          └─► watchfiles ──► SSE ──► Browser
```

## 6. Versioning

The outer repository is already a git repo. The agent auto-commits after
every turn where a file under `phase2/output/` was written or modified.
Only paths under `phase2/output/` are staged. Commit messages follow
`[agent] <summary>`.

`.gitignore` currently ignores `output/` globally (Phase 1 mapper
artifacts); we add `!phase2/output/` so Phase 2 artifacts are tracked.

## 7. Security & constraints

- `OPENAI_API_KEY` is loaded from `phase2/backend/.env`; never committed.
- Tool filesystem access is allow-listed to `phase2/output/` and
  `phase2/backend/uploads/<session_id>/`. Path traversal is rejected.
- `call_api` respects user-supplied headers (so the user can pass their
  own API key to the tool call); no secrets are persisted server-side.

## 8. Out of scope (for Phase 2)

- Handshake mapping (Phase 2.5)
- Running scheduled pipelines (Phase 3)
- ClickHouse / Nebius (Phase 4)
- Multi-user auth; this is a single-operator tool for now.

## 9. Acceptance criteria

1. Run `make -C phase2 dev`, open `http://localhost:3000`.
2. Upload a CSV (e.g. from `seeds/stripe/`) and ask *"Describe this table."*
3. Assistant streams a response; within the same turn, `description.md`
   and `columns.json` appear under `phase2/output/tables/<slug>/` and
   are highlighted in the Files tab.
4. A new commit appears in the Commits tab referencing those paths.
5. `git log -- phase2/output/` on the CLI shows the same commit.
