"""Minimal JWT dashboard (PRD §5.5) — extend with real run history + ClickHouse."""

from __future__ import annotations

import os

import jwt
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse


def run_dashboard(host: str, port: int) -> None:
    import uvicorn

    app = _build_app()
    uvicorn.run(app, host=host, port=port, log_level="info")


def _build_app() -> FastAPI:
    app = FastAPI(title="Mira run dashboard", version="0.1.0")
    secret = os.getenv("MIRA_JWT_SECRET", "dev-insecure-secret")

    @app.get("/dashboard", response_class=HTMLResponse)
    def dashboard(token: str = Query(..., description="HS256 JWT")):
        try:
            claims = jwt.decode(token, secret, algorithms=["HS256"])
        except jwt.PyJWTError as e:
            raise HTTPException(status_code=401, detail=str(e)) from e
        company = claims.get("company_id", "")
        run_id = claims.get("run_id", "")
        body = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Mira — {company}</title></head>
<body>
<h1>Onboarding run</h1>
<p><strong>company_id</strong>: {company}</p>
<p><strong>run_id</strong>: {run_id}</p>
<p>Wire this view to Supabase run history and ClickHouse metrics per PRD §5.5.</p>
</body></html>"""
        return HTMLResponse(body)

    @app.get("/healthz")
    def healthz():
        return JSONResponse({"ok": True})

    return app
