# Phase 2 — Exploration Chatbot

A ChatGPT-style web app for exploring unfamiliar datasets, APIs, and business
documents. It produces **Structured Table Descriptions** and **Structured Table
Column Info** artifacts, committed automatically to the outer git repo so you
can track discovery over time.

Implements [`phase2/phase2.prd`](./phase2.prd). Design spec:
[`docs/specs/2026-04-18-phase2-exploration-chatbot.md`](../docs/specs/2026-04-18-phase2-exploration-chatbot.md).

## What it does

- Chat UI (left) — ChatGPT-like streaming conversation with file upload, URL,
  and API-endpoint inputs.
- Workspace UI (right) — live file tree of `phase2/output/`, markdown/JSON/CSV
  viewer, and a commit-history timeline.
- Agent — OpenAI `gpt-4o` with a tool-calling loop. Tools:
  - `list_files`, `read_file`, `write_file`
  - `preview_csv`, `preview_json`
  - `fetch_url`, `call_api`
  - `git_commit` (scoped to `phase2/output/`)
- Versioning — after every agent turn that writes files, we auto-commit to the
  outer repo with message `[agent] <summary>`, scoped to `phase2/output/`.

## Directory layout

```text
phase2/
  backend/            FastAPI + OpenAI tool-calling loop
    app/
      main.py         FastAPI entry point
      settings.py     env-driven config
      agent.py        streaming tool-calling loop
      tools.py        tool implementations (allow-listed paths)
      git_ops.py      git commit / log helpers (scoped to output/)
      routes/
        chat.py       POST /api/chat  (SSE)
        uploads.py    POST /api/upload, GET /api/uploads/{sid}
        artifacts.py  GET /api/artifacts, GET /api/artifacts/{path}
        commits.py    GET /api/commits, GET /api/commits/{sha}
        events.py     GET /api/events (filesystem SSE)
    requirements.txt
    .env.example
  frontend/           Next.js 15 App Router + Tailwind
    app/page.tsx      split-pane layout
    components/
      Chat.tsx, Composer.tsx, MessageBubble.tsx
      WorkspacePanel.tsx, ArtifactTree.tsx, ArtifactViewer.tsx
      CommitHistory.tsx
    lib/              api client, SSE parser, shared types
  output/             agent-authored artifacts (auto-committed)
  Makefile            install / backend / frontend / dev targets
```

## Prerequisites

- Python 3.11+
- Node 20+ (with `npm`)
- A valid `OPENAI_API_KEY`

## Setup

```bash
cd phase2

# one-time install
make install

# configure OpenAI key
cp backend/.env.example backend/.env
$EDITOR backend/.env       # fill in OPENAI_API_KEY

# run both services (ports 8000 + 3000)
make dev
```

Then open http://localhost:3000.

Run services individually with `make backend` (FastAPI on :8000) or
`make frontend` (Next.js on :3000) in separate terminals.

Health check: `curl http://localhost:8000/healthz`.

## Output contract

For every table the agent identifies it writes two files under
`phase2/output/tables/<slug>/`:

- `description.md` — business purpose, row meaning, relationships,
  datasource, retrieval process.
- `columns.json` — per-column datatype, domain, unit, and natural-language
  description.

It also maintains `phase2/output/INDEX.md`, a running list of described tables.

## Security notes

- `OPENAI_API_KEY` is loaded from `phase2/backend/.env` and is git-ignored.
- Agent filesystem access is allow-listed to `phase2/output/` (writes) and
  `phase2/backend/uploads/<session_id>/` (reads). Path traversal is rejected.
- `call_api` forwards headers you provide so you can pass third-party API
  keys via chat; nothing is persisted server-side. Rotate any key you share
  with an agent once you're done exploring.

## External libraries / references

- **OpenAI Python SDK** — streaming Chat Completions with tool calls.
- **FastAPI + uvicorn** — HTTP + Server-Sent Events.
- **watchfiles** — filesystem watch driving the live workspace updates.
- **GitPython** — scoped commits back into the outer ERP repo.
- **Next.js 15 App Router + Tailwind + react-markdown** — ChatGPT-style UI.
- **merge.dev Accounting / CRM common models** — referenced by the system
  prompt as the downstream target for Phase 2.5 mapping (see
  [`docs/0001-prd.md`](../docs/0001-prd.md)).
