# Developer entry points. English, like everything else about the code -- the i18n rule covers
# what the coach reads in the UI and the CLI (English default, German opt-in), not the tooling
# (SPEC.md 2).
#
# The UI needs the `ui` extra; `dev` installs it too, so `make install` covers both.

VENV    := .venv
PY      := $(VENV)/bin/python
PIP     := $(VENV)/bin/pip
RUFF    := $(VENV)/bin/ruff
MYPY    := $(VENV)/bin/mypy
PYTEST  := $(PY) -m pytest
DP      := $(VENV)/bin/dancepartner

TEAM    ?= data/team.example.yaml
DANCER  ?= lukas-b
PORT    ?= 8501
DP_LANG ?= en
# GitHub Pages serves a project site under /<repo>/, never at the root.
BASE    ?= /dancepartner/

.DEFAULT_GOAL := help
.PHONY: help ui venv install fmt lint typecheck test cov check cli clean \
	wasm wasm-serve wasm-icons docker-build docker-up docker-down

help:  ## Show this help
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk -F':.*?## ' '{printf "  \033[1m%-12s\033[0m %s\n", $$1, $$2}'
	@echo
	@echo "  Variables:  TEAM=$(TEAM)  DANCER=$(DANCER)  PORT=$(PORT)  DP_LANG=$(DP_LANG)  BASE=$(BASE)"

## -- the UI ------------------------------------------------------------------------------

ui: $(VENV)  ## Start the Streamlit UI (make ui PORT=8600)
	@$(PY) -c 'import streamlit' 2>/dev/null || { \
		echo "streamlit is missing -- it is an extra, not a runtime dependency."; \
		echo "Install it with:  make install   (or: $(PIP) install -e '.[ui]')"; \
		exit 1; }
	@echo "Starting on http://localhost:$(PORT) -- Ctrl-C to stop."
	@# Run from the repository root: Home.py is the entry script, so Streamlit puts app/ on
	@# sys.path, which is how the pages import `common`.
	DANCEPARTNER_LANG=$(DP_LANG) $(VENV)/bin/streamlit run app/Home.py --server.port $(PORT)

## -- environment -------------------------------------------------------------------------

$(VENV):
	python3 -m venv $(VENV)

venv: $(VENV)  ## Create the virtualenv

install: $(VENV)  ## Install the package with dev + ui extras
	$(PIP) install -e '.[dev]'
	$(VENV)/bin/pre-commit install

## -- gates (the same ones CI runs) --------------------------------------------------------

fmt: ## Format the code
	$(RUFF) format .
	$(RUFF) check --fix .

lint: ## Check formatting and lint rules
	$(RUFF) format --check .
	$(RUFF) check .

typecheck: ## Run mypy --strict over src, tests and app
	$(MYPY)

test: ## Run the test suite
	$(PYTEST)

cov: ## Run the test suite with the coverage gate
	$(PYTEST) --cov=src/dancepartner --cov-report=term-missing --cov-fail-under=90

check: lint typecheck cov cli  ## Everything CI runs

## -- the CLI, as a smoke test -------------------------------------------------------------

cli: ## Run check/solve/explain against $(TEAM) (set DANCER for a different team)
	DANCEPARTNER_LANG=$(DP_LANG) $(DP) check $(TEAM)
	DANCEPARTNER_LANG=$(DP_LANG) $(DP) solve $(TEAM) --json /tmp/dancepartner-out.json
	DANCEPARTNER_LANG=$(DP_LANG) $(DP) explain $(TEAM) /tmp/dancepartner-out.json --dancer $(DANCER)
	DANCEPARTNER_LANG=de $(DP) check $(TEAM)

## -- deployment (SPEC.md 14) --------------------------------------------------------------

wasm: $(VENV)  ## Build the static browser bundle into wasm/dist
	$(PY) wasm/build_static.py --out wasm/dist --base-path $(BASE)

wasm-serve: $(VENV)  ## Build for the root path and serve it on http://localhost:8000
	$(PY) wasm/build_static.py --out wasm/dist --base-path /
	@echo "Serving the browser build on http://localhost:8000 -- Ctrl-C to stop."
	@# The first load pulls ~30 MB of Pyodide; the editor-only notice is the sign it worked.
	$(PY) -m http.server 8000 --directory wasm/dist

wasm-icons: $(VENV)  ## Redraw the PWA icons (they are committed; this only needs rerunning on a change)
	$(PY) wasm/make_icons.py

docker-build:  ## Build the server image locally
	docker build -f docker/Dockerfile -t dancepartner:local .

docker-up:  ## Start app + Caddy (needs docker/.env -- see docker/.env.example)
	docker compose -f docker/compose.yaml up -d --build

docker-down:  ## Stop them
	docker compose -f docker/compose.yaml down

clean: ## Remove caches and build artefacts
	rm -rf .mypy_cache .pytest_cache .ruff_cache .coverage htmlcov dist build wasm/dist
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
