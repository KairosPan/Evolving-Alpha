.PHONY: install dev api web test test-live build serve gen-api lint

VENV ?= .venv
PY := $(VENV)/bin/python
UVICORN := $(VENV)/bin/uvicorn
PYTEST := $(VENV)/bin/pytest

install:
	$(PY) -m pip install -e ".[dev]"
	cd apps/web && npm install

dev:
	@( trap 'kill 0' SIGINT; \
	   $(UVICORN) apps.api.main:app --reload --port 8000 & \
	   ( cd apps/web && npm run dev ) & \
	   wait )

api:
	$(UVICORN) apps.api.main:app --reload --port 8000

web:
	cd apps/web && npm run dev

gen-api:
	cd apps/web && npm run gen:api

test:
	$(PYTEST) -q --timeout=60
	cd apps/web && npm test

test-live:
	$(PYTEST) -q -m live

lint:
	$(VENV)/bin/ruff check .
	$(VENV)/bin/mypy apps/api src
	cd apps/web && npx tsc --noEmit && npm run lint

build:
	cd apps/web && npm run build

serve:
	$(UVICORN) apps.api.main:app --port 8000
