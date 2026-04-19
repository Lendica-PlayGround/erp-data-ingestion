"""Load short previews of user-supplied input files for codegen prompts."""

from __future__ import annotations

import csv
import json
from pathlib import Path


def _truncate_cell(s: str, max_cell: int) -> str:
    s = s.replace("\n", "\\n").replace("\r", "")
    if len(s) <= max_cell:
        return s
    return s[:max_cell] + "…"


def preview_csv(path: Path, *, max_rows: int = 25, max_cell: int = 400, delimiter: str = ",") -> str:
    lines: list[str] = []
    with path.open(newline="", encoding="utf-8", errors="replace") as f:
        reader = csv.reader(f, delimiter=delimiter)
        for i, row in enumerate(reader):
            if i >= max_rows:
                lines.append(f"... truncated after {max_rows} data rows ...")
                break
            trimmed = [_truncate_cell(c, max_cell) for c in row]
            sep = "\t" if delimiter == "\t" else ","
            lines.append(sep.join(trimmed))
    return "\n".join(lines)


def preview_text(path: Path, *, max_chars: int = 8000) -> str:
    raw = path.read_text(encoding="utf-8", errors="replace")
    if len(raw) <= max_chars:
        return raw
    return raw[:max_chars] + "\n... truncated ..."


def preview_path(path: Path) -> str:
    suf = path.suffix.lower()
    if suf == ".csv":
        return preview_csv(path)
    if suf == ".tsv":
        return preview_csv(path, delimiter="\t")
    if suf in (".json", ".jsonl"):
        try:
            return preview_text(path, max_chars=12000)
        except OSError as e:
            return f"<error reading {path}: {e}>"
    return preview_text(path, max_chars=8000)


def build_inputs_section(paths: list[Path]) -> str:
    parts: list[str] = []
    for p in paths:
        rp = p.resolve()
        if not rp.is_file():
            parts.append(f"## {rp}\n<MISSING FILE>\n")
            continue
        try:
            body = preview_path(rp)
        except OSError as e:
            parts.append(f"## {rp}\n<error: {e}>\n")
            continue
        parts.append(f"## {rp}\n```\n{body}\n```\n")
    return "\n".join(parts) if parts else "(no input files provided)\n"


def phase2_columns_snippets(phase2_output: Path, table_slugs: list[str]) -> str:
    """Include Phase 2 columns.json for each table so codegen sees dtypes/descriptions."""
    parts: list[str] = []
    root = phase2_output / "tables"
    for slug in table_slugs:
        cj = root / slug / "columns.json"
        if not cj.is_file():
            parts.append(f"### {slug}\n<no columns.json at {cj}>\n")
            continue
        try:
            data = json.loads(cj.read_text(encoding="utf-8"))
            parts.append(f"### {slug}\n```json\n{json.dumps(data, indent=2)[:20000]}\n```\n")
        except (OSError, json.JSONDecodeError) as e:
            parts.append(f"### {slug}\n<error reading columns.json: {e}>\n")
    return "\n".join(parts)
