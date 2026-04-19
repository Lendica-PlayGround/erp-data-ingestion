---
skill_id: open_pr
phase: 3
description: Commit connector workspace and open GitHub PR with IRR in body.
requires:
  bins: ["git"]
  env: ["GITHUB_TOKEN"]
---

# open_pr

The tool will create a PR. Branch naming: `connector/<company_id>/<source>/<mapping_version>`.

PR body will include the IRR markdown. On success, the tool will patch `phase3.pr_url`. Only then should you use `state_store` to move `state` from `code` → `dry_run`.
