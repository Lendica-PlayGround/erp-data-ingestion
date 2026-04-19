---
skill_id: generate_tests
phase: 3
description: Generate fixtures and tests for transforms, schema compliance, delta cursor.
requires:
  bins: ["uv"]
  env: []
---

# generate_tests

The tool will create `tests/fixtures/` with 3+ raw records per table, plus `test_transforms.py`, `test_schema_compliance.py`, `test_delta_cursor.py`.

Tests must be able to run with `uv run pytest` inside the connector workspace.
