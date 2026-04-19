"""GET /artifacts — tree + contents of phase2/output/."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..settings import get_settings

router = APIRouter()


@router.get("/artifacts")
async def list_artifacts() -> dict:
    root = get_settings().output_path
    root.mkdir(parents=True, exist_ok=True)
    files = []
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
    return {"files": files}


@router.get("/artifacts/{path:path}")
async def read_artifact(path: str) -> dict:
    root = get_settings().output_path
    if ".." in path.split("/"):
        raise HTTPException(400, "invalid path")
    target = (root / path).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError as exc:
        raise HTTPException(400, "path escapes output dir") from exc
    if not target.exists() or not target.is_file():
        raise HTTPException(404, "not found")
    data = target.read_bytes()
    try:
        text = data.decode("utf-8")
        binary = False
    except UnicodeDecodeError:
        text = ""
        binary = True
    return {
        "path": path,
        "size": len(data),
        "mtime": target.stat().st_mtime,
        "binary": binary,
        "content": text,
    }
