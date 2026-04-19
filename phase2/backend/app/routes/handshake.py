"""POST /handshake/run — Phase 2.5 handshake pipeline (map + codegen) for the UI."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..file_preview import content_payload
from ..settings import BACKEND_DIR, Settings, get_settings

log = logging.getLogger(__name__)

router = APIRouter()

_REPO_ROOT = BACKEND_DIR.parent.parent
_PHASE25 = _REPO_ROOT / "phase2.5"
_PHASE25_OUT = _PHASE25 / "output"
_MIDLAYER_V1 = _REPO_ROOT / "midlayer-schema-guide" / "midlayer" / "v1"
# Source-like uploads for codegen previews (any basename; matched by suffix only).
_SOURCE_SUFFIXES = frozenset({".csv", ".tsv", ".txt", ".json", ".jsonl", ".xlsx", ".xlsm"})
# Generated ``handshake_run_mapper.py`` uses csv.DictReader — only these are valid apply inputs.
_MAPPER_INPUT_SUFFIXES = frozenset({".csv", ".tsv", ".txt"})
_MAX_LOG_CHARS = 12_000


def _session_source_files(upload_root: Path) -> list[Path]:
    """All user-uploaded source previews under the session (names vary by client)."""
    if not upload_root.is_dir():
        return []
    out: list[Path] = []
    for p in upload_root.rglob("*"):
        if not p.is_file():
            continue
        if p.name.startswith("."):
            continue
        if p.suffix.lower() in _SOURCE_SUFFIXES:
            out.append(p)
    return sorted(out, key=lambda x: str(x).lower())


def _session_mapper_inputs(upload_root: Path) -> list[Path]:
    """Session files the CSV mapper can read (excludes XLSX/JSON used only for previews)."""
    if not upload_root.is_dir():
        return []
    out: list[Path] = []
    for p in upload_root.rglob("*"):
        if not p.is_file():
            continue
        if p.name.startswith("."):
            continue
        if p.suffix.lower() in _MAPPER_INPUT_SUFFIXES:
            out.append(p)
    return sorted(out, key=lambda x: str(x).lower())


class HandshakeRunBody(BaseModel):
    """Optional session id: CSV uploads under uploads/<session>/ are passed to codegen."""

    session_id: str = Field(default="")


class HandshakeApplyBody(BaseModel):
    """Optional session id: source CSVs under uploads/<session>/ are used as mapper inputs."""

    session_id: str = Field(default="")


def _truncate(s: str) -> str:
    s = s or ""
    if len(s) <= _MAX_LOG_CHARS:
        return s
    return s[: _MAX_LOG_CHARS] + "\n… [truncated]"


def _run_subprocess(
    argv: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout: int,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=env,
        timeout=timeout,
    )


def _resolve_handshake_json(_settings: Settings) -> Path | None:
    """Handshake mapping JSON lives only under ``phase2.5/output/``."""
    p = _PHASE25_OUT / "handshake_mapping.json"
    return p if p.is_file() else None


def _resolve_mapper_script(_settings: Settings) -> Path | None:
    """Generated mapper script lives only under ``phase2.5/output/``."""
    p = _PHASE25_OUT / "handshake_run_mapper.py"
    return p if p.is_file() else None


def _pick_input_for_table(uploads: list[Path], table: str) -> Path | None:
    """Match an upload to a mid-layer table name (basename heuristics)."""
    t = table.lower()
    scored: list[tuple[int, Path]] = []
    for p in uploads:
        s = p.stem.lower()
        if s == t:
            score = 100
        elif s.startswith(f"{t}_") or s.endswith(f"_{t}"):
            score = 85
        elif t in s:
            score = 70
        elif s.startswith(t) or s.endswith(t):
            score = 55
        else:
            continue
        scored.append((score, p))
    if not scored:
        return None
    scored.sort(key=lambda x: (-x[0], x[1].name.lower()))
    return scored[0][1]


def _phase2_table_csv(phase2_out: Path, phase2_table: str) -> Path | None:
    d = phase2_out / "tables" / phase2_table
    if not d.is_dir():
        return None
    csvs = sorted(d.glob("*.csv"))
    return csvs[0] if csvs else None


@router.get("/handshake/artifacts")
async def list_handshake_artifacts() -> dict:
    """List files under ``phase2.5/output/`` (handshake JSON, mapper, mapped CSVs)."""
    root = _PHASE25_OUT
    if not root.is_dir():
        return {"files": []}
    files: list[dict] = []
    try:
        for p in sorted(root.rglob("*")):
            if p.is_dir() or any(part.startswith(".") for part in p.relative_to(root).parts):
                continue
            stat = p.stat()
            files.append(
                {
                    "path": p.relative_to(root).as_posix(),
                    "size": stat.st_size,
                    "mtime": stat.st_mtime,
                }
            )
    except OSError as exc:
        raise HTTPException(500, f"cannot list phase2.5 output: {exc!s}") from exc
    return {"files": files}


@router.get("/handshake/content")
async def read_handshake_content(path: str = Query(..., min_length=1)) -> dict:
    """Read a file under ``phase2.5/output/`` (relative path)."""
    if ".." in path.split("/"):
        raise HTTPException(400, "invalid path")
    root = _PHASE25_OUT.resolve()
    target = (root / path).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise HTTPException(400, "path escapes phase2.5 output dir") from exc
    if not target.exists() or not target.is_file():
        raise HTTPException(404, "not found")
    return content_payload(path, target)


@router.post("/handshake/run")
async def run_handshake(body: HandshakeRunBody) -> dict:
    """Run map + codegen in a worker thread so ``subprocess.run`` does not block the event loop."""
    settings = get_settings()
    if not settings.openai_api_key.strip():
        raise HTTPException(
            503,
            "OPENAI_API_KEY is not configured on the Phase 2 backend.",
        )
    if not _PHASE25.is_dir():
        raise HTTPException(500, f"phase2.5 directory not found: {_PHASE25}")

    phase25_output = _PHASE25_OUT
    phase25_output.mkdir(parents=True, exist_ok=True)

    env: dict[str, str] = {k: v for k, v in os.environ.items() if isinstance(v, str)}
    env["OPENAI_API_KEY"] = settings.openai_api_key
    env["PYTHONPATH"] = str(_PHASE25)
    env["PHASE25_MODEL"] = settings.model  # align with Phase 2 model

    py = sys.executable
    steps: list[dict] = []

    phase2_out = settings.output_path.resolve()
    midlayer_v1 = _MIDLAYER_V1.resolve()
    handshake_json = (phase25_output / "handshake_mapping.json").resolve()

    # 1) map — explicit paths so we never rely on phase2.5/.env when spawned from the API
    map_argv = [
        py,
        "-m",
        "handshake_mapping",
        "map",
        "--phase2-output",
        str(phase2_out),
        "--midlayer-schema-dir",
        str(midlayer_v1),
        "--out",
        str(handshake_json),
        "--model",
        settings.model,
    ]
    try:
        r_map = await asyncio.to_thread(
            _run_subprocess,
            map_argv,
            cwd=_PHASE25,
            env=env,
            timeout=1200,
        )
    except subprocess.TimeoutExpired as exc:
        log.exception("handshake map timed out")
        raise HTTPException(504, "Handshake map step timed out (20 min).") from exc
    except Exception as exc:
        log.exception("handshake map subprocess failed")
        raise HTTPException(500, f"handshake map failed to start: {exc!s}") from exc
    steps.append(
        {
            "step": "map",
            "ok": r_map.returncode == 0,
            "returncode": r_map.returncode,
            "stdout": _truncate(r_map.stdout),
            "stderr": _truncate(r_map.stderr),
        }
    )
    if r_map.returncode != 0:
        log.warning(
            "handshake map failed rc=%s stderr=%s",
            r_map.returncode,
            (r_map.stderr or "")[:2000],
        )
        return {
            "ok": False,
            "map_ok": False,
            "codegen_ok": False,
            "steps": steps,
            "artifacts": [],
        }

    # 2) codegen — optional session CSVs as --input
    codegen_args: list[str] = [
        py,
        "-m",
        "handshake_mapping",
        "codegen",
        "--handshake",
        str(handshake_json),
        "--phase2-output",
        str(phase2_out),
        "--out",
        str((phase25_output / "handshake_run_mapper.py").resolve()),
        "--model",
        settings.model,
    ]
    sid = (body.session_id or "").strip()
    if sid:
        upload_root = (settings.upload_path / sid).resolve()
        for p in _session_source_files(upload_root):
            codegen_args.extend(["--input", str(p)])

    try:
        r_gen = await asyncio.to_thread(
            _run_subprocess,
            codegen_args,
            cwd=_PHASE25,
            env=env,
            timeout=1200,
        )
    except subprocess.TimeoutExpired as exc:
        log.exception("handshake codegen timed out")
        raise HTTPException(
            504,
            "Handshake codegen timed out (20 min). Column mapping may have completed; check phase2.5/output/.",
        ) from exc
    except Exception as exc:
        log.exception("handshake codegen subprocess failed")
        raise HTTPException(500, f"handshake codegen failed to start: {exc!s}") from exc
    steps.append(
        {
            "step": "codegen",
            "ok": r_gen.returncode == 0,
            "returncode": r_gen.returncode,
            "stdout": _truncate(r_gen.stdout),
            "stderr": _truncate(r_gen.stderr),
        }
    )

    codegen_ok = r_gen.returncode == 0
    if not codegen_ok:
        log.warning(
            "handshake codegen failed rc=%s stderr=%s",
            r_gen.returncode,
            (r_gen.stderr or "")[:2000],
        )

    artifacts: list[str] = []
    hj = phase25_output / "handshake_mapping.json"
    if hj.is_file():
        artifacts.append("phase2.5/output/handshake_mapping.json")
    if codegen_ok:
        hp = phase25_output / "handshake_run_mapper.py"
        if hp.is_file():
            artifacts.append("phase2.5/output/handshake_run_mapper.py")

    ok = codegen_ok
    return {
        "ok": ok,
        "map_ok": True,
        "codegen_ok": codegen_ok,
        "steps": steps,
        "artifacts": artifacts,
    }


@router.post("/handshake/apply")
async def apply_handshake(body: HandshakeApplyBody) -> dict:
    """Run ``handshake_run_mapper.py`` for each table; writes mid-layer CSVs under ``phase2.5/output/mapped/``."""
    settings = get_settings()
    mapper = _resolve_mapper_script(settings)
    if not mapper:
        raise HTTPException(
            503,
            "handshake_run_mapper.py not found. Run “Run handshake” (codegen) first.",
        )
    hj = _resolve_handshake_json(settings)
    if not hj:
        raise HTTPException(
            503,
            "handshake_mapping.json not found. Run handshake (map) first.",
        )

    try:
        mapping = json.loads(hj.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(500, f"cannot read handshake JSON: {exc!s}") from exc

    tables = mapping.get("tables") or []
    if not tables:
        raise HTTPException(400, "handshake_mapping.json has no tables.")

    table_entries = [e for e in tables if (e.get("midlayer_table") or "").strip()]
    n_mapped_tables = len(table_entries)

    sid = (body.session_id or "").strip()
    upload_root = (settings.upload_path / sid).resolve() if sid else None
    uploads = _session_mapper_inputs(upload_root) if upload_root and upload_root.is_dir() else []
    phase2_out = settings.output_path.resolve()

    mapped_dir = _PHASE25_OUT / "mapped"
    mapped_dir.mkdir(parents=True, exist_ok=True)

    py = sys.executable
    steps: list[dict] = []
    outputs: list[str] = []
    skipped: list[dict] = []

    for entry in tables:
        mid = (entry.get("midlayer_table") or "").strip()
        p2 = (entry.get("phase2_table") or "").strip()
        if not mid:
            continue
        input_path: Path | None = None
        from_upload = False
        if uploads:
            input_path = _pick_input_for_table(uploads, mid)
            if input_path is not None:
                from_upload = True
            elif len(uploads) == 1 and n_mapped_tables == 1:
                input_path = uploads[0]
                from_upload = True
        if input_path is None and not uploads:
            input_path = _phase2_table_csv(phase2_out, p2)
        if input_path is None:
            if uploads:
                reason = (
                    f"no session upload matched table {mid!r} — rename a CSV to include that "
                    f'table name (e.g. "{mid}.csv"), or use one CSV when the handshake maps '
                    "only one table."
                )
            else:
                reason = (
                    "no CSV/TSV/txt found — upload e.g. contacts.csv, or add .csv under "
                    "phase2/output/tables/<phase2_table>/"
                )
            skipped.append({"table": mid, "phase2_table": p2, "reason": reason})
            continue

        argv = [
            py,
            str(mapper),
            "--input",
            str(input_path),
            "--output",
            str(mapped_dir),
            "--table",
            mid,
        ]
        try:
            proc = await asyncio.to_thread(
                _run_subprocess,
                argv,
                cwd=mapper.parent,
                env={k: v for k, v in os.environ.items() if isinstance(v, str)},
                timeout=600,
            )
        except subprocess.TimeoutExpired as exc:
            log.exception("handshake apply timed out for table %s", mid)
            raise HTTPException(504, f"Mapper timed out for {mid}.") from exc
        except Exception as exc:
            log.exception("handshake apply subprocess failed for %s", mid)
            raise HTTPException(500, f"mapper failed to start for {mid}: {exc!s}") from exc

        out_rel = f"mapped/{mid}_mapped.csv"
        out_file = mapped_dir / f"{mid}_mapped.csv"
        ok = proc.returncode == 0 and out_file.is_file()
        if ok:
            outputs.append(out_rel)
        steps.append(
            {
                "table": mid,
                "input": str(input_path),
                "input_source": "session_upload" if from_upload else "phase2_output",
                "ok": ok,
                "returncode": proc.returncode,
                "stdout": _truncate(proc.stdout),
                "stderr": _truncate(proc.stderr),
            }
        )

    any_ok = any(s.get("ok") for s in steps)
    return {
        "ok": any_ok,
        "outputs": outputs,
        "skipped": skipped,
        "steps": steps,
        "mapped_dir": "phase2.5/output/mapped",
        "preview_dir": "phase2.5/output/mapped",
    }
