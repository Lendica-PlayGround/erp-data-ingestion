"""GET /events — SSE stream of filesystem change events in output/."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from watchfiles import Change, awatch

from ..settings import get_settings

router = APIRouter()

_CHANGE_NAMES = {Change.added: "added", Change.modified: "modified", Change.deleted: "deleted"}


@router.get("/events")
async def events() -> StreamingResponse:
    root = get_settings().output_path
    root.mkdir(parents=True, exist_ok=True)

    async def gen():
        yield f"data: {json.dumps({'type': 'hello'})}\n\n"
        try:
            async for changes in awatch(str(root), stop_event=None, recursive=True):
                for change, path in changes:
                    try:
                        rel = str(path)
                        if rel.startswith(str(root)):
                            rel = rel[len(str(root)):].lstrip("/")
                    except Exception:
                        rel = str(path)
                    yield (
                        "data: "
                        + json.dumps(
                            {
                                "type": "file_changed",
                                "change": _CHANGE_NAMES.get(change, "unknown"),
                                "path": rel,
                            }
                        )
                        + "\n\n"
                    )
        except asyncio.CancelledError:
            return

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
