---
skill_id: lock_contract
phase: 3
description: Freeze mapping_version and midlayer_schema_version in control plane.
requires:
  bins: []
  env: []
---

# lock_contract

Phase 3 step 1. Persist immutable mapping metadata to `mapping_versions` (via control plane) and set `phase3.contract_locked_at` on state.

Do not mutate `mapping_contract` after this step.
