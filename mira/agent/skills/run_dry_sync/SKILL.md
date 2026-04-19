---
skill_id: run_dry_sync
phase: 3
description: Execute connector in sandbox on ≤100 sample rows; write preview CSV + validation summary.
requires:
  bins: ["uv"]
  env: []
---

# run_dry_sync

The tool will run the generated connector against a capped sample. It will record row counts, validation summary, and preview paths under `phase3.dry_run`.

It will set `phase3.dry_run_errors` to an empty list. After this succeeds, use `state_store` to transition `state` from `dry_run` to `initial_sync`.
