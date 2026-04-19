"""Load mid-layer v1 column allow-lists and schema snippets for prompts."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MIDLAYER_GUIDE = _REPO_ROOT / "midlayer-schema-guide"
if _MIDLAYER_GUIDE.is_dir():
    sys.path.insert(0, str(_MIDLAYER_GUIDE))

from midlayer.v1.models import (  # type: ignore[import-not-found]
    TABLE_COLUMNS,
)


def table_columns() -> dict[str, list[str]]:
    return {k: list(v) for k, v in TABLE_COLUMNS.items()}


def schema_summary_json(midlayer_v1: Path, table: str) -> str:
    """Subset of JSON Schema `properties` for LLM context (types, descriptions, enums)."""
    fname = {"invoices": "invoice", "customers": "customer", "contacts": "contact"}[table]
    path = midlayer_v1 / f"{fname}.schema.json"
    if not path.is_file():
        raise FileNotFoundError(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    props = data.get("properties") or {}
    slim: dict[str, object] = {}
    for k, v in props.items():
        if not isinstance(v, dict):
            continue
        entry: dict[str, object] = {}
        if "type" in v:
            entry["type"] = v["type"]
        if v.get("description"):
            entry["description"] = v["description"]
        if v.get("enum"):
            entry["enum"] = v["enum"]
        if v.get("format"):
            entry["format"] = v["format"]
        if v.get("pattern"):
            entry["pattern"] = v["pattern"]
        slim[k] = entry
    return json.dumps(slim, indent=2, ensure_ascii=False)
