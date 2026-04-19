"""Apply mapping_contract transforms to raw dict rows (MVP: common ops only)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any


def apply_transforms(value: Any, transforms: list[dict[str, Any]]) -> Any:
    out = value
    for t in transforms:
        op = t.get("op")
        if op == "identity":
            continue
        if op == "divide":
            out = float(out) / float(t.get("by", 1))
        elif op == "uppercase":
            out = str(out).upper()
        elif op == "cast":
            to = t.get("to", "")
            if "decimal" in str(to).lower():
                out = str(Decimal(str(out)))
        else:
            out = value
    return out


def apply_field_mapping(row: dict[str, Any], fields: list[dict[str, Any]]) -> dict[str, Any]:
    mapped: dict[str, Any] = {}
    for f in fields:
        src = f.get("source_field")
        dst = f.get("midlayer_field")
        if src not in row:
            continue
        mapped[dst] = apply_transforms(row[src], list(f.get("transforms") or []))
    return mapped
