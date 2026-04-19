---
skill_id: issue_dashboard_jwt
phase: 3
description: Mint JWT scoped to (company_id, run_id); post magic login URL to Telegram.
requires:
  bins: []
  env: ["MIRA_JWT_SECRET"]
---

# issue_dashboard_jwt

The tool will mint a short-lived JWT including `company_id` and `run_id`. It will post `MIRA_DASHBOARD_BASE_URL/?token=...` to the group.

It will store `phase3.dashboard_url` on state for audit.
