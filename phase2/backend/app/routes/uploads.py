"""POST /upload — stores user files under uploads/<session_id>/."""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile

from ..file_preview import content_payload
from ..settings import get_settings

router = APIRouter()

SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")
MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB per file


def _safe_filename(name: str) -> str:
    name = Path(name).name  # strip any path components
    cleaned = SAFE_NAME.sub("_", name).strip("._") or "file"
    return cleaned[:200]


@router.post("/upload")
async def upload(
    session_id: str = Form(...),
    files: list[UploadFile] = File(...),
) -> dict:
    if not session_id.strip():
        raise HTTPException(400, "session_id is required")
    dest = get_settings().upload_path / session_id
    dest.mkdir(parents=True, exist_ok=True)

    saved: list[dict] = []
    for f in files:
        name = _safe_filename(f.filename or "upload")
        target = dest / name
        stem, suffix = target.stem, target.suffix
        i = 1
        while target.exists():
            target = dest / f"{stem}-{i}{suffix}"
            i += 1

        total = 0
        with target.open("wb") as out:
            while chunk := await f.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_UPLOAD_BYTES:
                    out.close()
                    target.unlink(missing_ok=True)
                    raise HTTPException(413, f"{name} exceeds 25 MB")
                out.write(chunk)
        saved.append(
            {
                "name": target.name,
                "path": f"uploads/{target.name}",
                "size": total,
                "content_type": f.content_type,
            }
        )
    return {"session_id": session_id, "files": saved}


@router.delete("/uploads/{session_id}")
async def delete_upload(session_id: str, path: str = Query(..., min_length=1)) -> dict:
    """Remove one uploaded file for this session. ``path`` is the client path
    like ``uploads/foo.csv`` (same as returned by POST /upload and GET).
    """
    raw = path.strip()
    if raw.startswith("uploads/"):
        rel = raw[len("uploads/") :].lstrip("/")
    else:
        rel = raw.lstrip("/")
    if not rel or ".." in Path(rel).parts:
        raise HTTPException(400, "invalid path")

    root = get_settings().upload_path / session_id
    target = (root / rel).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError as exc:
        raise HTTPException(400, "path escapes session dir") from exc
    if not target.is_file():
        raise HTTPException(404, "not found")
    target.unlink()
    return {"ok": True, "path": path}


@router.get("/uploads/{session_id}")
async def list_uploads(session_id: str) -> dict:
    root = get_settings().upload_path / session_id
    if not root.exists():
        return {"session_id": session_id, "files": []}
    files = [
        {
            "name": p.relative_to(root).as_posix(),
            "path": f"uploads/{p.relative_to(root).as_posix()}",
            "size": p.stat().st_size,
        }
        for p in sorted(root.rglob("*"))
        if p.is_file()
    ]
    return {"session_id": session_id, "files": files}


@router.get("/uploads/{session_id}/content")
async def read_upload_content(session_id: str, path: str = Query(..., min_length=1)) -> dict:
    """Return UTF-8 text or mark binary — same shape as ``GET /api/artifacts/{path}``."""
    raw = path.strip()
    if raw.startswith("uploads/"):
        rel = raw[len("uploads/") :].lstrip("/")
    else:
        rel = raw.lstrip("/")
    if not rel or ".." in Path(rel).parts:
        raise HTTPException(400, "invalid path")

    root = get_settings().upload_path / session_id
    target = (root / rel).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError as exc:
        raise HTTPException(400, "path escapes session dir") from exc
    if not target.exists() or not target.is_file():
        raise HTTPException(404, "not found")
    return content_payload(path, target)
