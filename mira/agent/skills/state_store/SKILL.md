---
skill_id: state_store
phase: cross_cutting
description: Single read/write path for onboarding_runs JSON; validates transitions.
requires:
  bins: []
  env: []
---

# state_store

Parameters:

- `run_id` (uuid string)
- `operation`: `get` | `patch`
- `patch_json`: JSON object merged into the document when patching (required for `patch`)
- `new_state`: optional explicit next state; validated against PRD §6.1

All other skills should call this tool instead of writing to Supabase directly.
