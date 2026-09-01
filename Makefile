.PHONY: setup run test lint clean help install-frontend run-frontend build-frontend

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

setup: ## Install backend dependencies and set up .env
	python -m pip install -e ".[dev]"
	@if [ ! -f .env ]; then cp .env.example .env; echo "Created .env — defaults to USE_MOCK=true (no API keys needed)"; fi
	mkdir -p data

run: ## Run the backend (single FastAPI app)
	@# See scripts/run_all.sh — .env is only loaded by the Python process
	@# itself (pydantic-settings), so API_HOST/API_PORT are pulled out here
	@# with grep/cut rather than sourced wholesale (.env commonly has values,
	@# like an app password, with unescaped spaces that aren't valid bash).
	bash -c 'cd backend && env_host=$$( { grep -E "^API_HOST=" ../.env || true; } 2>/dev/null | tail -1 | cut -d= -f2- | sed "s/[[:space:]]*#.*//"); env_port=$$( { grep -E "^API_PORT=" ../.env || true; } 2>/dev/null | tail -1 | cut -d= -f2- | sed "s/[[:space:]]*#.*//"); exec python -m uvicorn app.main:app --host "$${API_HOST:-$${env_host:-127.0.0.1}}" --port "$${API_PORT:-$${env_port:-8000}}" --reload'

test: ## Run backend tests (unit + golden-set matching regression)
	python -m pytest backend/tests/ -v

lint: ## Run linter
	ruff check backend/

health: ## Check backend health
	curl -sf http://localhost:8000/health && echo

install-frontend: ## Install frontend dependencies
	cd frontend && npm install

run-frontend: ## Run frontend dev server
	cd frontend && npm run dev

build-frontend: ## Build frontend for production
	cd frontend && npm run build

clean: ## Remove caches and build artifacts
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
