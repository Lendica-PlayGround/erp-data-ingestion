# Phase 2 exploration chatbot — dev orchestration.
#
# Targets:
#   make install       install backend + frontend deps
#   make backend       run FastAPI on :8000
#   make frontend      run Next.js on :3000
#   make dev           run both concurrently (requires GNU make; prefers foreman-like output)
#   make dev-reclaim   free :8000 then dev (use when make dev fails: port already in use)
#   make clean         remove caches / build output
#
# Requires: Python 3.11+, Node 20+, pnpm or npm.

SHELL := /bin/bash
BACKEND := backend
FRONTEND := frontend

PY ?= python3
PIP ?= $(PY) -m pip
NPM ?= npm

.PHONY: install backend frontend dev dev-reclaim clean install-backend install-frontend _check_port kill-backend-port

install: install-backend install-frontend

install-backend:
	cd $(BACKEND) && $(PY) -m venv .venv && . .venv/bin/activate && pip install --upgrade pip && pip install -r requirements.txt
	@echo
	@echo "Backend ready. Copy $(BACKEND)/.env.example to $(BACKEND)/.env and fill in OPENAI_API_KEY."

install-frontend:
	cd $(FRONTEND) && $(NPM) install

backend:
	cd $(BACKEND) && . .venv/bin/activate && uvicorn app.main:app --reload --port 8000

frontend:
	cd $(FRONTEND) && $(NPM) run dev

# Free :8000 when a previous uvicorn was left running (Ctrl-C sometimes leaves the listener).
kill-backend-port:
	@if ! command -v lsof >/dev/null 2>&1; then \
	  echo "lsof not found; free port 8000 manually or install lsof."; exit 1; \
	fi
	@pids=$$(lsof -ti:8000 2>/dev/null || true); \
	if [ -n "$$pids" ]; then \
	  echo "Stopping process(es) on port 8000: $$pids"; \
	  kill $$pids 2>/dev/null || true; \
	  for _ in 1 2 3 4 5 6 7 8 9 10; do \
	    lsof -ti:8000 >/dev/null 2>&1 || break; \
	    sleep 0.2; \
	  done; \
	  if lsof -ti:8000 >/dev/null 2>&1; then \
	    echo "Port still busy; sending SIGKILL..."; \
	    kill -9 $$(lsof -ti:8000 2>/dev/null) 2>/dev/null || true; \
	    sleep 0.3; \
	  fi; \
	  if lsof -ti:8000 >/dev/null 2>&1; then \
	    echo "Port 8000 still busy; try:  kill -9 \$$(lsof -ti:8000)"; \
	    exit 1; \
	  fi; \
	fi

# Fail fast if :8000 is taken — otherwise Next starts but /api/* (chat, uploads) is broken.
_check_port:
	@port=8000; \
	if command -v lsof >/dev/null 2>&1; then \
	  if lsof -ti:$$port >/dev/null 2>&1; then \
	    echo ""; \
	    echo "ERROR: Port $$port is already in use — uvicorn cannot start."; \
	    echo "The UI will load on :3000 but chat and uploads will not work."; \
	    echo "Fix: run  make dev-reclaim  or manually:  kill \$$(lsof -ti:$$port)  then  make dev"; \
	    echo ""; \
	    exit 1; \
	  fi; \
	fi

# Same as dev, but stops any process on :8000 first (typical fix after a stuck uvicorn).
dev-reclaim:
	@$(MAKE) kill-backend-port
	@$(MAKE) dev

dev: _check_port
	@echo "Starting backend (:8000) and frontend (:3000). Ctrl-C to stop both."
	@echo "If the UI shows 500 on /api/*, the API is not reachable — keep uvicorn running (check the terminal for import/pip errors)."
	@trap 'kill 0' EXIT; \
	( cd $(BACKEND) && . .venv/bin/activate && uvicorn app.main:app --reload --port 8000 ) & \
	( cd $(FRONTEND) && $(NPM) run dev ) & \
	wait

clean:
	rm -rf $(BACKEND)/.venv $(BACKEND)/__pycache__ $(BACKEND)/app/__pycache__ $(BACKEND)/app/routes/__pycache__
	rm -rf $(FRONTEND)/node_modules $(FRONTEND)/.next
