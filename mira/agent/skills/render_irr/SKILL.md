---
skill_id: render_irr
phase: 2.5
description: Render Implementation Readiness Review markdown and post to Telegram.
requires:
  bins: []
  env: []
---

# render_irr

The tool will render PRD §4.3 IRR from the current `mapping_contract`, `table_descriptions`, and `source`.

It will post the markdown to the onboarding Telegram group and keep a copy in `phase3.irr_markdown` for PR bodies.
