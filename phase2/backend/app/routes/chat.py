"""POST /chat — streams agent events as SSE."""

from __future__ import annotations

import json
from typing import Any, Literal

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..agent import run_agent
from ..settings import get_settings

router = APIRouter()


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1)
    messages: list[ChatMessage]


def _session_uploads(session_id: str) -> list[str]:
    up_root = get_settings().upload_path / session_id
    if not up_root.exists():
        return []
    return sorted(
        str(p.relative_to(up_root).as_posix())
        for p in up_root.rglob("*")
        if p.is_file()
    )


@router.post("/chat")
async def chat(req: ChatRequest) -> StreamingResponse:
    history: list[dict[str, Any]] = [m.model_dump() for m in req.messages]
    uploads = _session_uploads(req.session_id)

    async def gen():
        yield f"data: {json.dumps({'type': 'start'})}\n\n"
        try:
            async for event in run_agent(req.session_id, history, uploads):
                yield event.sse()
        except Exception as exc:  # noqa: BLE001
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
        yield f"data: {json.dumps({'type': 'end'})}\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
