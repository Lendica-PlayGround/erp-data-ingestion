---
skill_id: generate_connector
phase: 3
description: Fill connector templates under connectors/<company>/<source>/ in the run workspace.
requires:
  bins: ["uv"]
  env: []
---

# generate_connector

The tool will generate the layout in PRD §5.3 using `framework/` interfaces. Output will match template filenames:

`connector_config.yaml`, `source_adapter.py`, `transform_*.py`, `sync_runner.py`, `validation.py`, `tests/`, `README.md`.
