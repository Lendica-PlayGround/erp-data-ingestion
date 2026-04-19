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

When enough is known to move on, call the tool with `system`, `access_method`, and `tables_csv`. The tool will populate `source.system`, `source.access_method`, and `tables_in_scope`. It will also transition `state` from `intake` to `research` if `source.system` is not `unknown` and transitions allow it.
