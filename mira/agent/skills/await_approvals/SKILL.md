---
skill_id: await_approvals
phase: 2.5
description: Block until customer and FDE approvals exist on state (slash commands).
requires:
  bins: []
  env: []
---

# await_approvals

Call this tool to check if both customer and FDE approvals are present.

Do not use `state_store` to transition to `code` until the tool returns `ok=True`.

The Telegram runtime records these approvals via `state_store` when gated slash commands fire.
