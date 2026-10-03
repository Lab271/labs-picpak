UV ?= uv
FRAME ?=
F = $(if $(FRAME),-f $(FRAME),)

.DEFAULT_GOAL := help
.PHONY: help dev test lint format type check scan frames info list push delete identify clean

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

scan: ## Find PicPak frames in range (wake the frame first)
	$(UV) run picpak scan

frames: ## Show named frames
	$(UV) run picpak frames

info: ## Battery, firmware, serial, image count [FRAME=name]
	$(UV) run picpak info $(F)

list: ## Occupied image slots [FRAME=name]
	$(UV) run picpak list $(F)

push: ## Send an image: make push IMG=photo.jpg [FRAME=name] [ARGS=--no-dither]
	@test -n "$(IMG)" || { echo "usage: make push IMG=path [FRAME=name] [ARGS=...]"; exit 1; }
	$(UV) run picpak push "$(IMG)" $(F) $(ARGS)

delete: ## Delete one slot: make delete SLOT=1 [FRAME=name]
	@test -n "$(SLOT)" || { echo "usage: make delete SLOT=n [FRAME=name]"; exit 1; }
	$(UV) run picpak delete $(SLOT) $(F)

identify: ## Show the frame's name on its screen [FRAME=name]
	$(UV) run picpak identify $(F)

clean: ## Remove caches and build output
	rm -rf .pytest_cache .ruff_cache .coverage build dist
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
