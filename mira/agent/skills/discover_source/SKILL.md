---
skill_id: discover_source
phase: 2
description: Guided intake; read/write source.* and tables_in_scope on the onboarding state.
requires:
  bins: []
  env: []
---

# discover_source

Run the Phase 2 intake conversation. Before each question, call `state_store` to read the current document and skip questions already answered.

Persist any newly learned objective, success criteria, stakeholder role, constraints, or open questions while you are in intake. Do not treat those as disposable chat-only details.

When enough is known to move on, call the tool with `system`, `access_method`, and `tables_csv`. The tool will populate `source.system`, `source.access_method`, and `tables_in_scope`. It will also transition `state` from `intake` to `research` if `source.system` is not `unknown` and transitions allow it.

As soon as the ERP/source system is known, stop re-running the cold-start ritual. Shift into targeted follow-up questions and research.
