"""OpenAI structured mapping from Phase 2 columns to mid-layer v1."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Literal

from openai import OpenAI
from pydantic import BaseModel, Field

from .midlayer_catalog import schema_summary_json, table_columns
from .models import ColumnHandshake, TableHandshake
from .phase2_loader import Phase2Table

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a data integration architect. Map columns from an exploration-phase \
dataset (Phase 2) onto the canonical mid-layer schema (merge.dev-aligned v1).

Rules:
- For each Phase 2 column, choose one or more **exact** mid-layer column names \
from the allowed list for the chosen `midlayer_table`, OR use the literal \
`other` as the only entry when nothing fits (store in `_unmapped` downstream).
- Align **data types** and semantics: strings, ISO 8601 UTC for datetimes, \
booleans, JSON-in-string for complex fields per schema descriptions.
- `processing_steps` must list concrete steps: casts, parsing, trimming, \
currency/decimal rules (4 decimal places for money strings), timezone, \
enum normalization, JSON minification, etc.
- `confidence` is 0–1 for how sure you are about the mapping for that column.
- Choose `midlayer_table` as one of: invoices, customers, contacts — whichever \
best matches the Phase 2 table name, description, and columns.
- Output **every** Phase 2 column exactly once; do not invent columns.
"""


class _MapPayload(BaseModel):
    """Response wrapper for OpenAI `parse` (root must be an object)."""

    phase2_table: str
    midlayer_table: Literal["invoices", "customers", "contacts"] = Field(
        description="Target mid-layer MVP table.",
    )
    routing_note: str = ""
    columns: list[ColumnHandshake]


def _normalize_slug(slug: str) -> str:
    s = slug.strip().lower().rstrip("/")
    aliases = {
        "invoice": "invoices",
        "contact": "contacts",
        "customer": "customers",
    }
    return aliases.get(s, s)


def _infer_default_table(slug: str) -> str | None:
    s = _normalize_slug(slug)
    if s in ("invoices", "customers", "contacts"):
        return s
    return None


def _build_user_message(
    pt: Phase2Table,
    midlayer_v1: Path,
    hint_table: str | None,
) -> str:
    hint = (
        f"\nHint: the explorer named this table `{pt.slug}`; "
        f"the best mid-layer target is likely `{hint_table}`.\n"
        if hint_table
        else ""
    )
    desc = (
        (pt.description_text or "")[:12000]
        if pt.description_text
        else "(no description.md)"
    )
    cols_json = json.dumps(pt.columns_doc, indent=2, ensure_ascii=False)
    guide_path = midlayer_v1.parent.parent / "midlayer-schema-guide.md"
    guide_blurb = ""
    if guide_path.is_file():
        g = guide_path.read_text(encoding="utf-8")[:6000]
        guide_blurb = f"\n## Schema guide excerpt\n{g}\n"

    schema_blocks = "\n\n".join(
        f"### {t}\n{schema_summary_json(midlayer_v1, t)}"
        for t in ("invoices", "customers", "contacts")
    )

    return f"""\
## Phase 2 table
Slug / table field: `{pt.slug}`
{hint}
## description.md
{desc}

## columns.json
{cols_json}

## Mid-layer JSON Schema properties (all MVP tables; pick `midlayer_table` then only use names from that table)
{schema_blocks}
{guide_blurb}
"""


def map_phase2_table(
    pt: Phase2Table,
    *,
    client: OpenAI,
    model: str,
    midlayer_v1: Path,
) -> TableHandshake:
    hint = _infer_default_table(pt.slug)
    user_msg = _build_user_message(pt, midlayer_v1, hint)

    allowed_by_table = table_columns()
    # Include allow-lists so the model cannot hallucinate names.
    allow_json = json.dumps(allowed_by_table, indent=2, ensure_ascii=False)

    user_msg_full = (
        user_msg
        + "\n## Allowed mid-layer column names per table\n"
        + allow_json
        + "\nUse only names from the list for `midlayer_table`, or `other`.\n"
        + f"\nSet `phase2_table` in your response exactly to: `{pt.slug}`\n"
    )

    completion = client.beta.chat.completions.parse(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg_full},
        ],
        response_format=_MapPayload,
        temperature=0.1,
    )
    msg = completion.choices[0].message
    if msg.refusal:
        raise RuntimeError(f"Model refused: {msg.refusal}")
    parsed = msg.parsed
    if not parsed:
        raise RuntimeError("No parsed response from model")

    payload = parsed
    if payload.phase2_table != pt.slug:
        log.warning(
            "phase2_table mismatch: model=%r artifact=%r (using artifact slug)",
            payload.phase2_table,
            pt.slug,
        )
    mt = _normalize_slug(payload.midlayer_table)
    if mt not in allowed_by_table:
        raise ValueError(f"Invalid midlayer_table from model: {payload.midlayer_table}")

    # Re-validate column names against chosen table.
    allowed = set(allowed_by_table[mt])
    phase2_names = [c["name"] for c in pt.columns_doc.get("columns", [])]
    out_cols: list[ColumnHandshake] = []
    by_name = {c.phase2_column: c for c in payload.columns}
    for name in phase2_names:
        ch = by_name.get(name)
        if not ch:
            raise RuntimeError(f"Missing mapping for Phase 2 column: {name}")
        mids = ch.midlayer_columns
        if mids == ["other"]:
            pass
        else:
            bad = [m for m in mids if m not in allowed]
            if bad:
                raise ValueError(f"Invalid mid-layer columns for {name}: {bad}")
        out_cols.append(
            ColumnHandshake(
                phase2_column=ch.phase2_column,
                midlayer_columns=ch.midlayer_columns,
                processing_steps=ch.processing_steps,
                confidence=ch.confidence,
            )
        )
    extra = set(by_name.keys()) - set(phase2_names)
    if extra:
        raise RuntimeError(f"Extra mappings not in Phase 2 columns: {extra}")

    return TableHandshake(
        phase2_table=pt.slug,
        midlayer_table=mt,  # type: ignore[arg-type]
        routing_note=payload.routing_note,
        columns=out_cols,
    )
