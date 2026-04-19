"""POST /handshake/run — Phase 2.5 handshake pipeline (map + codegen) for the UI."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..settings import BACKEND_DIR, Settings, get_settings

log = logging.getLogger(__name__)

router = APIRouter()

_REPO_ROOT = BACKEND_DIR.parent.parent
_PHASE25 = _REPO_ROOT / "phase2.5"
_MIDLAYER_V1 = _REPO_ROOT / "midlayer-schema-guide" / "midlayer" / "v1"
# Source-like uploads for codegen previews (any basename; matched by suffix only).
_SOURCE_SUFFIXES = frozenset({".csv", ".tsv", ".txt", ".json", ".jsonl"})
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


def _resolve_handshake_json(settings: Settings) -> Path | None:
    """Prefer published workspace copy; fall back to phase2.5/output."""
    p = settings.output_path / "handshake" / "handshake_mapping.json"
    if p.is_file():
        return p
    alt = _PHASE25 / "output" / "handshake_mapping.json"
    if alt.is_file():
        return alt
    return None


def _resolve_mapper_script(settings: Settings) -> Path | None:
    p = settings.output_path / "handshake" / "handshake_run_mapper.py"
    if p.is_file():
        return p
    alt = _PHASE25 / "output" / "handshake_run_mapper.py"
    if alt.is_file():
        return alt
    return None


def _pick_input_for_table(uploads: list[Path], table: str) -> Path | None:
    """Match an upload to a mid-layer table name (basename heuristics)."""
    t = table.lower()
    for p in uploads:
        if p.stem.lower() == t:
            return p
    for p in uploads:
        s = p.stem.lower()
        if s.startswith(t + "_") or s.endswith("_" + t):
            return p
    for p in uploads:
        if t in p.stem.lower():
            return p
    return None


def _phase2_table_csv(phase2_out: Path, phase2_table: str) -> Path | None:
    d = phase2_out / "tables" / phase2_table
    if not d.is_dir():
        return None
    csvs = sorted(d.glob("*.csv"))
    return csvs[0] if csvs else None


def _publish_artifacts(
    phase25_output: Path,
    output_root: Path,
    *,
    codegen_ok: bool,
) -> list[str]:
    dest = output_root / "handshake"
    dest.mkdir(parents=True, exist_ok=True)
    out: list[str] = []
    hj = phase25_output / "handshake_mapping.json"
    if hj.is_file():
        shutil.copy2(hj, dest / "handshake_mapping.json")
        out.append("handshake/handshake_mapping.json")
    if codegen_ok:
        hp = phase25_output / "handshake_run_mapper.py"
        if hp.is_file():
            shutil.copy2(hp, dest / "handshake_run_mapper.py")
            out.append("handshake/handshake_run_mapper.py")
    return out


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

    phase25_output = _PHASE25 / "output"
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
    artifacts = _publish_artifacts(
        phase25_output,
        settings.output_path,
        codegen_ok=codegen_ok,
    )

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
    """Run ``handshake_run_mapper.py`` for each table, writing mid-layer CSV previews under `handshake/preview/`."""
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

    sid = (body.session_id or "").strip()
    upload_root = (settings.upload_path / sid).resolve() if sid else None
    uploads = _session_source_files(upload_root) if upload_root and upload_root.is_dir() else []
    phase2_out = settings.output_path.resolve()

    preview_dir = settings.output_path / "handshake" / "preview"
    preview_dir.mkdir(parents=True, exist_ok=True)

    py = sys.executable
    steps: list[dict] = []
    outputs: list[str] = []
    skipped: list[dict] = []

    for entry in tables:
        mid = (entry.get("midlayer_table") or "").strip()
        p2 = (entry.get("phase2_table") or "").strip()
        if not mid:
            continue
        input_path = None
        if uploads:
            input_path = _pick_input_for_table(uploads, mid)
        if input_path is None and p2:
            input_path = _phase2_table_csv(phase2_out, p2)
        if input_path is None:
            skipped.append(
                {
                    "table": mid,
                    "phase2_table": p2,
                    "reason": "no CSV found (upload a file whose name matches the table, "
                    "or place a .csv under output/tables/<phase2_table>/)",
                }
            )
            continue

        argv = [
            py,
            str(mapper),
            "--input",
            str(input_path),
            "--output",
            str(preview_dir),
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

        out_rel = f"handshake/preview/{mid}_mapped.csv"
        out_file = preview_dir / f"{mid}_mapped.csv"
        ok = proc.returncode == 0 and out_file.is_file()
        if ok:
            outputs.append(out_rel)
        steps.append(
            {
                "table": mid,
                "input": str(input_path),
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
        "preview_dir": "handshake/preview",
    }
