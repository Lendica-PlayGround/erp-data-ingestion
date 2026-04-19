"""Mid-layer CSV writer enforcing `docs/0002-phase1-midlayer-csv-contract.md`."""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Any, Sequence


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_csv_with_meta(
    rows: Sequence[dict[str, Any]],
    fieldnames: Sequence[str],
    csv_path: Path,
    *,
    mapping_version: str,
    source_run_id: str,
    schema_version: str = "v1",
) -> dict[str, Any]:
    """Write UTF-8 CSV + sidecar meta.json; returns manifest fragment."""
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    buf = StringIO()
    w = csv.DictWriter(buf, fieldnames=list(fieldnames), extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in fieldnames})
    body = buf.getvalue().encode("utf-8")
    csv_path.write_bytes(body)
    meta = {
        "schema_version": schema_version,
        "row_count": len(rows),
        "sha256": sha256_bytes(body),
        "source_run_id": source_run_id,
        "mapping_version": mapping_version,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    meta_path = csv_path.with_suffix(".meta.json")
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta
