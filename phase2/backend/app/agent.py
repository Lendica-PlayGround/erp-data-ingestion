"""Exploration agent.

A single-model tool-calling loop against OpenAI's Chat Completions API.
Emits granular events (``token``, ``tool_start``, ``tool_result``,
``commit``, ``done``) so the frontend can render a ChatGPT-style
streaming UI with inline tool-call cards.

We use the OpenAI SDK directly (rather than LangGraph) because the
single-agent case doesn't need graph orchestration and direct access
to the streaming deltas lets us emit per-tool-call events cleanly.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, AsyncIterator

from openai import AsyncOpenAI

from . import git_ops
from .settings import get_settings
from .tools import ToolContext, ToolError, build_tool_specs, dispatch

log = logging.getLogger(__name__)

MAX_TOOL_ITERATIONS = 12

SYSTEM_PROMPT = """\
You are the Phase 2 Exploration Agent for an agentic ERP data ingestion
system. The user wants to understand an unfamiliar dataset, API, or
business document so it can later be mapped to a canonical mid-layer
schema (merge.dev Accounting / CRM common models).

You work by:
1. Inspecting what the user gave you (uploaded files, URLs, API
   endpoints, free-text guidance).
2. Calling tools to read/preview files, fetch documentation URLs, or
   call the user's APIs.
3. Writing *structured artifacts* to `output/` and committing them.

## Artifact contract (IMPORTANT)

For every logical table you identify, write TWO files:

### a) `output/tables/<slug>/description.md`

```
# <Human Table Name>

## Summary
<1-3 sentences on the business process this table represents.>

## Row meaning
<What a single row represents.>

## Relationships
<How this table links to other tables (foreign keys, joins).>

## Datasource
<Where you got this information: filename, URL, API endpoint.>

## Retrieval process
<How one would pull this dataset: endpoint, pagination, filters,
incremental cursor field, rate limits.>
```

### b) `output/tables/<slug>/columns.json`

```json
{
  "table": "<slug>",
  "columns": [
    {
      "name": "<field_name>",
      "datatype": "string | integer | number | boolean | date | datetime | object | array",
      "domain": {
        "kind": "categories | range | regex | text",
        "values": ["..."],                  // when kind = categories
        "min": 0, "max": null,              // when kind = range
        "pattern": "^INV-[0-9]+$",          // when kind = regex
        "missing": "null | empty_string | sentinel:<value>"
      },
      "unit": {
        "kind": "currency | percent | scale | identifier | category | degree | text | count | datetime | none",
        "code": "USD",                      // when kind = currency
        "scale_min": 1, "scale_max": 5      // when kind = scale
      },
      "description": "Natural-language summary of the field."
    }
  ]
}
```

Also maintain `output/INDEX.md` — a simple bulleted list of the tables
you have described so far, newest first, each linking to its
`description.md`.

## Operating rules

- After writing artifacts for a table, call `git_commit` with a short
  message like `describe invoices table`. The commit is scoped to
  `phase2/output/` automatically.
- When you are unsure, ask the user a clarifying question rather than
  guessing. Phase 2 optimizes for accuracy, not speed.
- When the user gives you an API key, pass it via the `headers`
  argument of `call_api` (never log or echo it back).
- Keep your written prose concise and technical.
"""


@dataclass
class AgentEvent:
    type: str
    data: dict[str, Any]

    def sse(self) -> str:
        payload = json.dumps({"type": self.type, **self.data}, default=str)
        return f"data: {payload}\n\n"


def _client() -> AsyncOpenAI:
    key = get_settings().openai_api_key
    if not key:
        raise RuntimeError("OPENAI_API_KEY is not configured")
    return AsyncOpenAI(api_key=key)


def build_messages(
    history: list[dict[str, Any]],
    session_uploads: list[str] | None,
) -> list[dict[str, Any]]:
    uploads_note = ""
    if session_uploads:
        listing = "\n".join(f"- uploads/{p}" for p in session_uploads)
        uploads_note = (
            "\n\nFiles the user has uploaded this session (readable via "
            "`read_file`, `preview_csv`, `preview_json`):\n" + listing
        )
    return [
        {"role": "system", "content": SYSTEM_PROMPT + uploads_note},
        *history,
    ]


async def run_agent(
    session_id: str,
    history: list[dict[str, Any]],
    session_uploads: list[str] | None = None,
) -> AsyncIterator[AgentEvent]:
    """Drive the agent loop, yielding SSE events."""
    settings = get_settings()
    client = _client()
    ctx = ToolContext(session_id=session_id)
    tools = build_tool_specs()
    messages = build_messages(history, session_uploads)

    for iteration in range(MAX_TOOL_ITERATIONS):
        tool_calls_accum: dict[int, dict[str, Any]] = {}
        assistant_text_parts: list[str] = []
        finish_reason: str | None = None

        try:
            stream = await client.chat.completions.create(
                model=settings.model,
                messages=messages,
                tools=tools,
                stream=True,
                temperature=0.2,
            )
        except Exception as exc:  # noqa: BLE001
            log.exception("openai stream failed")
            yield AgentEvent("error", {"message": str(exc)})
            return

        async for chunk in stream:
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            delta = choice.delta
            if delta.content:
                assistant_text_parts.append(delta.content)
                yield AgentEvent("token", {"text": delta.content})
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    slot = tool_calls_accum.setdefault(
                        tc.index,
                        {"id": None, "name": "", "arguments": ""},
                    )
                    if tc.id:
                        slot["id"] = tc.id
                    if tc.function and tc.function.name:
                        slot["name"] += tc.function.name
                    if tc.function and tc.function.arguments:
                        slot["arguments"] += tc.function.arguments
            if choice.finish_reason:
                finish_reason = choice.finish_reason

        assistant_text = "".join(assistant_text_parts)

        if not tool_calls_accum:
            messages.append({"role": "assistant", "content": assistant_text})
            yield AgentEvent("done", {"finish_reason": finish_reason or "stop"})
            return

        tool_call_list = [
            {
                "id": v["id"] or f"call_{i}",
                "type": "function",
                "function": {
                    "name": v["name"],
                    "arguments": v["arguments"] or "{}",
                },
            }
            for i, v in sorted(tool_calls_accum.items())
        ]
        messages.append(
            {
                "role": "assistant",
                "content": assistant_text or None,
                "tool_calls": tool_call_list,
            }
        )

        for tc in tool_call_list:
            name = tc["function"]["name"]
            raw_args = tc["function"]["arguments"]
            try:
                args = json.loads(raw_args or "{}")
            except json.JSONDecodeError:
                args = {}
            yield AgentEvent(
                "tool_start",
                {"id": tc["id"], "name": name, "arguments": args},
            )
            try:
                result = dispatch(ctx, name, args)
            except ToolError as exc:
                result = json.dumps({"error": str(exc)})
                yield AgentEvent(
                    "tool_result",
                    {"id": tc["id"], "name": name, "ok": False, "result": str(exc)},
                )
            else:
                yield AgentEvent(
                    "tool_result",
                    {
                        "id": tc["id"],
                        "name": name,
                        "ok": True,
                        "result": _truncate(result, 4000),
                    },
                )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "name": name,
                    "content": result,
                }
            )

        # Auto-commit any writes made this turn if the agent didn't
        # commit them explicitly.
        if ctx.written_paths:
            record = git_ops.commit_output(
                "[agent] update " + ", ".join(
                    p.name for p in list(ctx.written_paths)[:4]
                ),
                paths=list(ctx.written_paths),
            )
            ctx.written_paths.clear()
            if record is not None:
                yield AgentEvent(
                    "commit",
                    {
                        "sha": record.short_sha,
                        "message": record.message,
                        "files": record.files,
                    },
                )

    yield AgentEvent(
        "error",
        {"message": f"tool iteration limit ({MAX_TOOL_ITERATIONS}) reached"},
    )


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"... [truncated {len(text) - limit} chars]"
