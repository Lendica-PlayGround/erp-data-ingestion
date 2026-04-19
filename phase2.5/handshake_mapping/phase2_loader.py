"""Load Phase 2 exploration artifacts (columns.json + optional description.md)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class Phase2Table:
    slug: str
    columns_path: Path
    columns_doc: Dict[str, Any]
    description_text: Optional[str]


def discover_tables(phase2_output: Path) -> List["Phase2Table"]:
    tables_root = phase2_output / "tables"
    if not tables_root.is_dir():
        raise FileNotFoundError(f"No tables directory: {tables_root}")

    out: List[Phase2Table] = []
    for sub in sorted(tables_root.iterdir(), key=lambda p: p.name.lower()):
        if not sub.is_dir():
            continue
        cj = sub / "columns.json"
        if not cj.is_file():
            continue
        raw = json.loads(cj.read_text(encoding="utf-8"))
        desc_path = sub / "description.md"
        desc = desc_path.read_text(encoding="utf-8") if desc_path.is_file() else None
        slug = str(raw.get("table") or sub.name)
        out.append(
            Phase2Table(
                slug=slug,
                columns_path=cj,
                columns_doc=raw,
                description_text=desc,
            )
        )
    return out
