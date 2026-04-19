"""FastAPI entry point for the Phase 2 exploration backend."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import artifacts, chat, commits, events, handshake, uploads
from .settings import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Phase 2 Exploration Agent", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin, "http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/healthz")
    async def healthz() -> dict:
        return {
            "ok": True,
            "model": settings.model,
            "output_dir": str(settings.output_path),
            "has_openai_key": bool(settings.openai_api_key),
        }

    app.include_router(chat.router, prefix="/api")
    app.include_router(uploads.router, prefix="/api")
    app.include_router(artifacts.router, prefix="/api")
    app.include_router(commits.router, prefix="/api")
    app.include_router(events.router, prefix="/api")
    app.include_router(handshake.router, prefix="/api")
    return app


app = create_app()
