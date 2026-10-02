UV ?= uv

.DEFAULT_GOAL := help
.PHONY: help dev test lint format type check scan clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[32m%-10s\033[0m %s\n", $$1, $$2}'

dev: ## Install the package and dev tools into .venv
	$(UV) sync

test: ## Run the unit tests with coverage
	$(UV) run pytest --cov=labs_picpak --cov-report=term-missing

lint: ## Lint with ruff
	$(UV) run ruff check src tests

format: ## Format with ruff
	$(UV) run ruff format src tests
	$(UV) run ruff check --fix src tests

type: ## Type-check with pyright
	$(UV) run pyright

check: lint type test ## Lint, type-check and test

scan: ## Find PicPak frames in range
	$(UV) run picpak scan

clean: ## Remove caches and build output
	rm -rf .pytest_cache .ruff_cache .coverage build dist
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
