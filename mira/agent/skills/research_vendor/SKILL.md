---
skill_id: research_vendor
phase: 2
description: Fetch vendor docs and quirks; write artifacts_collected.
requires:
  bins: ["uv"]
  env: ["TAVILY_API_KEY"]
---

# research_vendor

The tool will collect official API docs, likely access paths, and known quirks for `source.system`.

It will write entries to `artifacts_collected` with `kind: api_doc_url` references, persist a `research_summary`, and store a `recommended_plan` with the most likely onboarding path plus the next missing fact to ask for.

If live research APIs are unavailable, it should still store useful heuristic guidance for common systems and record the research gap instead of hallucinating certainty.
