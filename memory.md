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

### What was tried
- 2026-04-18: Added root `README.md` and `memory.md`
- 2026-04-18: Created a design spec for documentation and process rules in `docs/specs/2026-04-18-documentation-process-rules-design.md`
- 2026-04-18: Created an implementation plan in `docs/superpowers/plans/2026-04-18-documentation-process-rules.md`
- 2026-04-18: Implemented Phase 2 Exploration Chatbot under `phase2/` — FastAPI backend (`phase2/backend/`) with OpenAI streaming tool-calling loop; Next.js 15 frontend (`phase2/frontend/`) with split-pane chat + live workspace. Artifacts are written to `phase2/output/` and auto-committed to the outer repo (scoped). Spec: `docs/specs/2026-04-18-phase2-exploration-chatbot.md`. Root `.gitignore` was updated with `!phase2/output/` so agent-authored artifacts stay tracked despite the repo-wide `output/` ignore.

### Phase 2 durable context
- `OPENAI_API_KEY` lives in `phase2/backend/.env` (git-ignored). `.env.example` documents other knobs (`PHASE2_MODEL`, `PHASE2_OUTPUT_DIR`, `PHASE2_UPLOAD_DIR`, `PHASE2_FRONTEND_ORIGIN`).
- Agent tool filesystem access is allow-listed: writes to `phase2/output/`, reads from `phase2/backend/uploads/<session_id>/`. Path traversal is rejected in `phase2/backend/app/tools.py::_resolve_safe`.
- Auto-commits only stage paths under `phase2/output/`; see `phase2/backend/app/git_ops.py::commit_output`.
- Frontend proxies `/api/*` to `http://127.0.0.1:8000` via `phase2/frontend/next.config.mjs`.
- Output contract: per table, write `phase2/output/tables/<slug>/description.md` + `columns.json`, plus a running `phase2/output/INDEX.md`. The contract is encoded in the system prompt at `phase2/backend/app/agent.py::SYSTEM_PROMPT`.
