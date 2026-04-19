"""Minimal JWT dashboard (PRD §5.5) — extend with real run history + ClickHouse."""

from __future__ import annotations

import os
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse

from agent.runtime.phase4_service import service_from_env


def run_dashboard(host: str, port: int) -> None:
    import uvicorn

    app = _build_app()
    uvicorn.run(app, host=host, port=port, log_level="info")


def _build_app() -> FastAPI:
    app = FastAPI(title="Mira run dashboard", version="0.1.0")
    secret = os.getenv("MIRA_JWT_SECRET", "dev-insecure-secret")

    def _decode_claims(token: str) -> dict[str, str]:
        try:
            claims = jwt.decode(token, secret, algorithms=["HS256"])
        except jwt.PyJWTError as e:
            raise HTTPException(status_code=401, detail=str(e)) from e
        return claims

    @app.get("/dashboard", response_class=HTMLResponse)
    def dashboard(token: str = Query(..., description="HS256 JWT")):
        claims = _decode_claims(token)
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

    @app.get("/dashboard/phase4", response_class=HTMLResponse)
    def phase4_dashboard(token: Annotated[str, Query(description="HS256 JWT")]):
        claims = _decode_claims(token)
        company = claims.get("company_id", "")
        run_id = claims.get("run_id", "")
        body = f"""<!doctype html>
<html>
  <head>
    <meta charset="utf-8">
    <title>Phase 4 Demo — {company}</title>
  </head>
  <body>
    <h1>Phase 4 Demo</h1>
    <p><strong>company_id</strong>: {company}</p>
    <p><strong>run_id</strong>: {run_id}</p>
    <button id="start-btn">Start Phase 4 Demo</button>
    <pre id="summary"></pre>
    <pre id="events"></pre>
    <script>
      const token = new URLSearchParams(window.location.search).get("token");
      let pollHandle = null;

      async function loadState() {{
        const state = await fetch(`/api/phase4/state?token=${{token}}`).then((r) => r.json());
        const events = await fetch(`/api/phase4/events?token=${{token}}`).then((r) => r.json());
        document.getElementById("summary").textContent = JSON.stringify(state, null, 2);
        document.getElementById("events").textContent = JSON.stringify(events, null, 2);
        if (state.status === "running") {{
          if (!pollHandle) {{
            pollHandle = setInterval(loadState, 3000);
          }}
        }} else if (pollHandle) {{
          clearInterval(pollHandle);
          pollHandle = null;
        }}
      }}

      document.getElementById("start-btn").addEventListener("click", async () => {{
        await fetch(`/api/phase4/start?token=${{token}}`, {{ method: "POST" }});
        loadState();
      }});

      loadState();
    </script>
  </body>
</html>"""
        return HTMLResponse(body)

    @app.get("/api/phase4/state")
    def phase4_state(token: Annotated[str, Query(description="HS256 JWT")]):
        claims = _decode_claims(token)
        service = service_from_env()
        try:
            state = service.get_state(run_id=UUID(claims["run_id"]))
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        return JSONResponse(state)

    @app.get("/api/phase4/events")
    def phase4_events(token: Annotated[str, Query(description="HS256 JWT")]):
        claims = _decode_claims(token)
        service = service_from_env()
        events = service.list_events(run_id=UUID(claims["run_id"]))
        return JSONResponse(events)

    @app.post("/api/phase4/start")
    def phase4_start(
        background_tasks: BackgroundTasks,
        token: Annotated[str, Query(description="HS256 JWT")],
    ):
        claims = _decode_claims(token)
        service = service_from_env()
        try:
            phase4 = service.start_demo(
                run_id=UUID(claims["run_id"]),
                company_id=claims["company_id"],
            )
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e)) from e
        background_tasks.add_task(service.run_demo, run_id=UUID(claims["run_id"]))
        return JSONResponse(phase4)

    @app.get("/healthz")
    def healthz():
        return JSONResponse({"ok": True})

    return app
