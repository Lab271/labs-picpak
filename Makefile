UV ?= uv
FRAME ?=
F = $(if $(FRAME),-f $(FRAME),)

.DEFAULT_GOAL := help
.PHONY: help scan frames info list push delete pull rename show now identify dashboard export import \
        dev test lint format type check clean

##@ Operations (wake the frame first; FRAME=name when you have more than one)

scan: ## Find frames in range
	$(UV) run picpak scan

frames: ## Named frames and where the state lives
	$(UV) run picpak frames

info: ## Battery, firmware, serial, image count
	$(UV) run picpak info $(F)

list: ## Slots with source, date and status (MD5-checked)
	$(UV) run picpak list $(F)

push: ## Send an image: IMG=photo.jpg [ARGS=--no-dither]
	@test -n "$(IMG)" || { echo "usage: make push IMG=path [FRAME=name] [ARGS=...]"; exit 1; }
	$(UV) run picpak push "$(IMG)" $(F) $(ARGS)

delete: ## Delete a slot on the frame and its record: SLOT=n
	@test -n "$(SLOT)" || { echo "usage: make delete SLOT=n [FRAME=name]"; exit 1; }
	$(UV) run picpak delete $(SLOT) $(F)

pull: ## Download a stored image (not in shipping firmware yet): SLOT=n
	@test -n "$(SLOT)" || { echo "usage: make pull SLOT=n [FRAME=name]"; exit 1; }
	$(UV) run picpak pull $(SLOT) $(F)

rename: ## Rename a frame, keeping its records: OLD=name NEW=name [ARGS=--on-device]
	@test -n "$(OLD)" -a -n "$(NEW)" || { echo "usage: make rename OLD=name NEW=name [ARGS=--on-device]"; exit 1; }
	$(UV) run picpak rename "$(OLD)" "$(NEW)" $(ARGS)

show: ## Put a stored slot on the screen: SLOT=n
	@test -n "$(SLOT)" || { echo "usage: make show SLOT=n [FRAME=name]"; exit 1; }
	$(UV) run picpak show $(SLOT) $(F)

now: ## What the screen shows now
	$(UV) run picpak now $(F)

identify: ## Show the frame's name on its screen
	$(UV) run picpak identify $(F)

dashboard: ## Write and open the HTML overview of all frames
	$(UV) run picpak dashboard

export: ## Save names, records and previews for another machine: FILE=picpak.zip
	$(UV) run picpak export "$(or $(FILE),picpak-export.zip)"

import: ## Load an export (merge): FILE=picpak.zip [ARGS=--replace]
	@test -n "$(FILE)" || { echo "usage: make import FILE=path [ARGS=--replace]"; exit 1; }
	$(UV) run picpak import "$(FILE)" $(ARGS)

##@ Build

dev: ## Install the package and dev tools into .venv
	$(UV) sync

check: lint type test ## Lint, type-check and test

test: ## Run the unit tests with coverage
	$(UV) run pytest --cov=labs_picpak --cov-report=term-missing

lint: ## Lint with ruff
	$(UV) run ruff check src tests

format: ## Format with ruff
	$(UV) run ruff format src tests
	$(UV) run ruff check --fix src tests

type: ## Type-check with pyright
	$(UV) run pyright

##@ Support

help: ## Show this help
	@awk 'BEGIN {FS = ":.*?## "} \
	  /^##@/ {printf "\n\033[1m%s\033[0m\n", substr($$0, 5); next} \
	  /^[a-zA-Z_-]+:.*?## / {printf "  \033[32m%-10s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

clean: ## Remove caches and build output
	rm -rf .pytest_cache .ruff_cache .coverage build dist
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
