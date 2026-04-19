---
skill_id: draft_mapping
phase: 2.5
description: Draft mapping_contract JSON with confidences and transforms toward mid-layer v1.
requires:
  bins: []
  env: []
---

# draft_mapping

Build `mapping_contract` per PRD §4.2:

- `midlayer_schema_version` must match published schemas (e.g. `v1`).
- Every mapped field lists transforms explicitly (e.g. cents → major units for Stripe).
- Unmapped source fields must be listed per object; nothing is silently dropped (mid-layer `_unmapped`).

When the draft is complete and Phase 2 exit criteria are met, use `state_store` to transition `state` to `map` then `awaiting_approval` only through legal transitions.
