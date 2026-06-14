# Veritas (claims-auditor) — developer entrypoints.
# These targets are intentionally thin in Phase 0 (stubs). They define the
# contract a fresh Claude Code session can rely on as modules are implemented.

.PHONY: help install test lint fmt run-api db-up db-down

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Create/refresh the dev environment (editable install + dev extras)
	python -m pip install -e ".[dev]"

test: ## Run the test suite
	pytest

lint: ## Lint with ruff
	ruff check .

fmt: ## Auto-format with ruff
	ruff format .
	ruff check --fix .

run-api: ## Run the FastAPI app (stub until the api module is implemented)
	uvicorn claims_auditor.api.app:app --reload --host 0.0.0.0 --port 8000

db-up: ## Start Postgres+pgvector (and the app service) via docker-compose
	docker compose up -d db

db-down: ## Stop docker-compose services
	docker compose down
