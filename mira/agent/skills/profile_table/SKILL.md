---
skill_id: profile_table
phase: 2
description: Produce Table + Column descriptions for one table from samples and docs.
requires:
  bins: []
  env: []
---

# profile_table

For a single table in `tables_in_scope`:

1. Provide the `table_descriptions` entry for that table as `table_json` (summary, row_grain, linkages, datasource, pull_process, known_quirks).
2. Provide `column_descriptions` for every observed column as `columns_json` (array of objects with datatype, domain, semantic_role, nl_summary).

The tool will merge these results idempotently into the state.
