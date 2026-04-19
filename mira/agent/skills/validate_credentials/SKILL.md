---
skill_id: validate_credentials
phase: 2
description: Accept credentials via vault reference; probe source; set auth_status. Never log secrets.
requires:
  bins: []
  env: []
---

# validate_credentials

1. Accept only references (vault id / secret name) or opaque handles — never raw secrets in transcripts.
2. Call the tool with the vault reference. For the MVP, you can pass `probe_ok=True` to simulate a successful probe.
3. The tool will patch `source.auth_status` to `validated` or `failed`.
