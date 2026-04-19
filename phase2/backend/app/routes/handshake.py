"""POST /handshake/run — Phase 2.5 handshake pipeline (map + codegen) for the UI."""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..settings import BACKEND_DIR, get_settings

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
