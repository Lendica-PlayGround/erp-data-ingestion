---
skill_id: research_vendor
phase: 2
description: Fetch vendor docs and quirks; write artifacts_collected.
requires:
  bins: ["uv"]
  env: ["TAVILY_API_KEY"]
---

# research_vendor

The tool will use web research (e.g. Tavily) to collect official API docs, pagination patterns, and known quirks for `source.system`.

It will write entries to `artifacts_collected` with `kind: api_doc_url` or `api_response_sample` references.

If research APIs are unavailable, it will add a `blocker` with `needs: research` instead of hallucinating.
