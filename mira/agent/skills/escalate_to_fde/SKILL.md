---
skill_id: escalate_to_fde
phase: cross_cutting
description: Post @FDE mention with structured blocker payload in Telegram.
requires:
  bins: []
  env: []
---

# escalate_to_fde

The tool will send a concise message tagging the FDE with: run id, state, blocker codes, and requested action.

It will append to `blockers` on state and transition the state to `failed`.
