# Phase 2 exploration chatbot — dev orchestration.
#
# Targets:
#   make install       install backend + frontend deps
#   make backend       run FastAPI on :8000
#   make frontend      run Next.js on :3000
#   make dev           run both concurrently (requires GNU make; prefers foreman-like output)
#   make clean         remove caches / build output
#
# Requires: Python 3.11+, Node 20+, pnpm or npm.

SHELL := /bin/bash
BACKEND := backend
FRONTEND := frontend

PY ?= python3
PIP ?= $(PY) -m pip
NPM ?= npm

.PHONY: install backend frontend dev clean install-backend install-frontend

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

dev:
	@echo "Starting backend (:8000) and frontend (:3000). Ctrl-C to stop both."
	@trap 'kill 0' EXIT; \
	( cd $(BACKEND) && . .venv/bin/activate && uvicorn app.main:app --reload --port 8000 ) & \
	( cd $(FRONTEND) && $(NPM) run dev ) & \
	wait

clean:
	rm -rf $(BACKEND)/.venv $(BACKEND)/__pycache__ $(BACKEND)/app/__pycache__ $(BACKEND)/app/routes/__pycache__
	rm -rf $(FRONTEND)/node_modules $(FRONTEND)/.next
