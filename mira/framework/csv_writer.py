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


def _sha256_path(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def write_csv_with_meta(
    rows: Sequence[dict[str, Any]],
    fieldnames: Sequence[str],
    csv_path: Path,
    *,
    mapping_version: str,
    source_run_id: str,
    schema_version: str = "v1",
    storage_key: str | None = None,
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
        "storage_key": storage_key,
    }
    meta_path = csv_path.with_suffix(".meta.json")
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return {
        **meta,
        "csv_path": str(csv_path),
        "meta_path": str(meta_path),
        "meta_sha256": _sha256_path(meta_path),
    }


def build_artifact_manifest(
    *,
    company_id: str,
    run_id: str,
    load_batch_id: str,
    artifacts: dict[str, Path],
    mapped_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    artifact_prefix = f"company_id={company_id}/run_id={run_id}/batch_id={load_batch_id}"
    manifest_artifacts: dict[str, dict[str, Any]] = {}

    for artifact_type, path in artifacts.items():
        manifest_artifacts[artifact_type] = {
            "storage_key": f"{artifact_prefix}/{artifact_type}/{path.name}",
            "sha256": _sha256_path(path),
        }

    if mapped_meta is not None and "mapped" in manifest_artifacts:
        manifest_artifacts["mapped"]["meta_path"] = mapped_meta.get("meta_path")
        manifest_artifacts["mapped"]["meta_sha256"] = mapped_meta.get("meta_sha256")

    return {
        "artifact_prefix": artifact_prefix,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "artifacts": manifest_artifacts,
    }
