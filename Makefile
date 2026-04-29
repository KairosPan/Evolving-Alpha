.PHONY: install dev api web test test-live build serve gen-api lint

install:
	pip install -e ".[dev]"
	cd apps/web && npm install

dev:
	@( trap 'kill 0' SIGINT; \
	   uvicorn apps.api.main:app --reload --port 8000 & \
	   ( cd apps/web && npm run dev ) & \
	   wait )

api:
	uvicorn apps.api.main:app --reload --port 8000

web:
	cd apps/web && npm run dev

gen-api:
	cd apps/web && npm run gen:api

test:
	pytest -q --timeout=60
	cd apps/web && npm test

test-live:
	pytest -q -m live

lint:
	ruff check .
	mypy apps/api src
	cd apps/web && npx tsc --noEmit && npm run lint

build:
	cd apps/web && npm run build

serve:
	uvicorn apps.api.main:app --port 8000
