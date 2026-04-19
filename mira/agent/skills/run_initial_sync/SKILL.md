---
skill_id: run_initial_sync
phase: 3
description: Full historical backfill to midlayer-csv bucket per 0002 layout.
requires:
  bins: ["uv"]
  env: ["SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"]
---

# run_initial_sync

The tool will write CSVs and sidecars to `midlayer-csv/<company>/<table>/initial/...` and emit `_manifest` metadata.

It will patch `phase3.initial_sync_manifest` with paths and checksums. After this succeeds, use `state_store` to transition `state` from `initial_sync` to `scheduled`.
