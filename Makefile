# OpenClaw Orchestration Stack Makefile
# Common commands for development and deployment

.PHONY: help install install-dev test lint format type-check check clean build docker-build docker-up docker-down docs migrate

# Default target
.DEFAULT_GOAL := help

# Variables
PYTHON := python3.11
PIP := pip
PYTEST := pytest
DOCKER_COMPOSE := docker-compose
PROJECT_NAME := openclaw

# ==============================================================================
# Help
# ==============================================================================

help: ## Show this help message
	@echo "OpenClaw Orchestration Stack - Available Commands:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ==============================================================================
# Installation
# ==============================================================================

install: ## Install production dependencies
	$(PIP) install -r requirements.txt

install-dev: ## Install development dependencies
	$(PIP) install -r requirements.txt
	$(PIP) install -r requirements-dev.txt

install-pre-commit: ## Install pre-commit hooks
	pre-commit install

# ==============================================================================
# Development
# ==============================================================================

dev: ## Start development server with auto-reload
	$(PYTHON) -m uvicorn openclaw.src.api:app --reload --host 0.0.0.0 --port 8000

dev-worker: ## Start development worker
	$(PYTHON) -m devclaw_runner.src.worker

dev-n8n: ## Start n8n for development
	n8n

dev-all: ## Start all services for development (requires tmux or multiple terminals)
	@echo "Starting all services..."
	@echo "1. Start API: make dev"
	@echo "2. Start Worker: make dev-worker"
	@echo "3. Start n8n: make dev-n8n"

# ==============================================================================
# Testing
# ==============================================================================

test: ## Run all tests
	$(PYTEST)

test-unit: ## Run unit tests only
	$(PYTEST) tests/unit/

test-integration: ## Run integration tests
	$(PYTEST) tests/integration/

test-e2e: ## Run end-to-end tests
	$(PYTEST) tests/e2e/

test-coverage: ## Run tests with coverage report
	$(PYTEST) --cov=openclaw --cov=devclaw_runner --cov=symphony_bridge --cov-report=html --cov-report=term

test-docs: ## Run documentation tests
	$(PYTEST) docs/tests/

test-watch: ## Run tests in watch mode
	$(PYTEST) -f

# ==============================================================================
# Code Quality
# ==============================================================================

lint: ## Run linting checks (flake8, pylint)
	flake8 openclaw devclaw_runner symphony_bridge shared
	pylint openclaw devclaw_runner symphony_bridge shared

format: ## Format code with black and isort
	black openclaw devclaw_runner symphony_bridge shared tests docs
	isort openclaw devclaw_runner symphony_bridge shared tests docs

format-check: ## Check code formatting without modifying files
	black --check openclaw devclaw_runner symphony_bridge shared tests docs
	isort --check-only openclaw devclaw_runner symphony_bridge shared tests docs

type-check: ## Run type checking with mypy
	mypy openclaw devclaw_runner symphony_bridge shared

check: format-check lint type-check test ## Run all checks (format, lint, type-check, test)

# ==============================================================================
# Database
# ==============================================================================

migrate: ## Run database migrations
	$(PYTHON) shared/migrations/runner.py migrate

migrate-status: ## Check migration status
	$(PYTHON) shared/migrations/runner.py status

migrate-create: ## Create a new migration (use: make migrate-create NAME=description)
	$(PYTHON) shared/migrations/runner.py create --name $(NAME)

db-backup: ## Backup database
	mkdir -p backups
	cp data/openclaw.db backups/openclaw.db.$(shell date +%Y%m%d_%H%M%S)

db-restore: ## Restore database from backup (use: make db-restore FILE=backups/...)
	cp $(FILE) data/openclaw.db

db-reset: ## Reset database (WARNING: DATA LOSS!)
	@echo "WARNING: This will delete all data!"
	@read -p "Are you sure? [y/N] " confirm && [ $$confirm = y ]
	rm -f data/openclaw.db data/openclaw.db-*
	$(PYTHON) shared/migrations/runner.py migrate

# ==============================================================================
# Docker
# ==============================================================================

docker-build: ## Build Docker images
	$(DOCKER_COMPOSE) -f docker/docker-compose.yml build

docker-up: ## Start Docker containers
	$(DOCKER_COMPOSE) -f docker/docker-compose.yml up -d

docker-down: ## Stop Docker containers
	$(DOCKER_COMPOSE) -f docker/docker-compose.yml down

docker-logs: ## View Docker logs
	$(DOCKER_COMPOSE) -f docker/docker-compose.yml logs -f

docker-clean: ## Remove Docker containers and volumes
	$(DOCKER_COMPOSE) -f docker/docker-compose.yml down -v
	docker system prune -f

# ==============================================================================
# Kubernetes
# ==============================================================================

k8s-deploy: ## Deploy to Kubernetes
	kubectl apply -k k8s/

k8s-delete: ## Delete Kubernetes deployment
	kubectl delete -k k8s/

k8s-status: ## Check Kubernetes deployment status
	kubectl get all -n openclaw

k8s-logs: ## View Kubernetes logs
	kubectl logs -n openclaw -l app.kubernetes.io/name=openclaw --tail=100 -f

# ==============================================================================
# Documentation
# ==============================================================================

docs-build: ## Build documentation
	cd docs && make html

docs-serve: ## Serve documentation locally
	cd docs/_build/html && $(PYTHON) -m http.server 8080

docs-clean: ## Clean documentation build
	cd docs && make clean

# ==============================================================================
# Utilities
# ==============================================================================

clean: ## Clean generated files and caches
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name ".coverage" -delete
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -exec rm -rf {} +
	find . -type d -name "htmlcov" -exec rm -rf {} +
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type d -name "dist" -exec rm -rf {} +
	find . -type d -name "build" -exec rm -rf {} +

venv: ## Create virtual environment
	$(PYTHON) -m venv venv
	@echo "Run 'source venv/bin/activate' to activate"

update-deps: ## Update dependencies
	$(PIP) install --upgrade -r requirements.txt
	$(PIP) install --upgrade -r requirements-dev.txt

security-check: ## Run security checks
	safety check
	bandit -r openclaw devclaw_runner symphony_bridge

# ==============================================================================
# Release
# ==============================================================================

version: ## Show current version
	@grep -E '^version' pyproject.toml | head -1

bump-version: ## Bump version (use: make bump-version VERSION=1.2.3)
	@echo "Bumping version to $(VERSION)"
	# Update version in pyproject.toml
	sed -i 's/^version = ".*"/version = "$(VERSION)"/' pyproject.toml
	# Update version in __init__.py files
	find openclaw devclaw_runner symphony_bridge -name "__init__.py" -exec \
		sed -i 's/__version__ = ".*"/__version__ = "$(VERSION)"/' {} \;

git-tag: ## Create git tag (use: make git-tag VERSION=1.2.3)
	git tag -a v$(VERSION) -m "Release v$(VERSION)"
	git push origin v$(VERSION)

release: bump-version git-tag ## Create a new release
	@echo "Release v$(VERSION) created"
	@echo "Next steps:"
	@echo "1. Build Docker images: make docker-build"
	@echo "2. Push Docker images: docker push openclaw/api:$(VERSION)"
	@echo "3. Create GitHub release with release notes"

# ==============================================================================
# Health Checks
# ==============================================================================

health: ## Check API health
	curl -s http://localhost:8000/health | jq

health-n8n: ## Check n8n health
	curl -s http://localhost:5678/healthz

status: ## Check service status
	@echo "=== API Status ==="
	@curl -s http://localhost:8000/health | jq -r '.status' || echo "API: Down"
	@echo ""
	@echo "=== Database ==="
	@$(PYTHON) -c "from shared.db import execute; print('Database: OK')" 2>/dev/null || echo "Database: Error"
	@echo ""
	@echo "=== Queue Depth ==="
	@$(PYTHON) -c "from shared.db import execute; result = execute('SELECT status, COUNT(*) as count FROM tasks GROUP BY status'); print('\n'.join([f'{r[\"status\"]}: {r[\"count\"]}' for r in result]))" 2>/dev/null || echo "Queue: Error"

# ==============================================================================
# Aliases
# ==============================================================================

run: dev ## Alias for dev
start: docker-up ## Alias for docker-up
stop: docker-down ## Alias for docker-down
restart: docker-down docker-up ## Restart Docker containers
build: docker-build ## Alias for docker-build
ci: check test ## Run CI checks

# ==============================================================================
# Custom Commands
# ==============================================================================

# Add your custom commands below
