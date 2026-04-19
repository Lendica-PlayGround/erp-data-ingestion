---
skill_id: schedule_delta_sync
phase: 3
description: Generate Airflow DAG, register cursor state for daily delta.
requires:
  bins: ["uv"]
  env: []
---

# schedule_delta_sync

The tool will use `framework.scheduling` to emit a DAG file into the repo’s Airflow dags path (project-specific). It will store cursor field and cadence from `mapping_contract.sync_strategy.delta`.
