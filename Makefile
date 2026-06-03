# GoldMind AI — common developer tasks.
.DEFAULT_GOAL := help
PY ?= python

.PHONY: help install install-dev lint format type test cov run-api graph backtest \
        db-up db-schema up down logs clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

install: ## Install runtime deps
	$(PY) -m pip install -r requirements.txt

install-dev: ## Install runtime + dev deps and the package (editable)
	$(PY) -m pip install -r requirements.txt -r requirements-dev.txt -e .

lint: ## Ruff lint
	ruff check src tests

format: ## Ruff format
	ruff format src tests

type: ## Mypy type-check
	mypy src

test: ## Run unit tests
	pytest -q

cov: ## Run tests with coverage
	pytest --cov=goldmind --cov-report=term-missing

run-api: ## Run the FastAPI control plane locally
	uvicorn goldmind.api.main:app --reload --port 8000

graph: ## Print the LangGraph workflow (mermaid) to stdout
	$(PY) -m goldmind.graph.workflow --print-mermaid

backtest: ## Run a sample backtest (see goldmind.backtest)
	$(PY) -m goldmind.backtest.run --help

db-schema: ## Print the SQL schema
	$(PY) -c "import importlib.resources as r; print(r.files('goldmind.db').joinpath('schema.sql').read_text())"

up: ## docker compose up (full stack)
	docker compose up -d --build

down: ## docker compose down
	docker compose down

logs: ## Tail compose logs
	docker compose logs -f --tail=100

clean: ## Remove caches and build artifacts
	rm -rf .pytest_cache .ruff_cache .mypy_cache build dist *.egg-info
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
