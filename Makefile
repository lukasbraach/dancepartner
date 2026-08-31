# Developer entry points. English, like everything else about the code -- the German-only rule
# covers what the coach reads in the UI and the CLI, not the tooling (SPEC.md 2).
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

.DEFAULT_GOAL := help
.PHONY: help ui venv install fmt lint typecheck test cov check cli clean

help:  ## Show this help
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk -F':.*?## ' '{printf "  \033[1m%-12s\033[0m %s\n", $$1, $$2}'
	@echo
	@echo "  Variables:  TEAM=$(TEAM)  DANCER=$(DANCER)  PORT=$(PORT)"

## -- the UI ------------------------------------------------------------------------------

ui: $(VENV)  ## Start the Streamlit UI (make ui PORT=8600)
	@$(PY) -c 'import streamlit' 2>/dev/null || { \
		echo "streamlit is missing -- it is an extra, not a runtime dependency."; \
		echo "Install it with:  make install   (or: $(PIP) install -e '.[ui]')"; \
		exit 1; }
	@echo "Starting on http://localhost:$(PORT) -- Ctrl-C to stop."
	@# Run from the repository root: Home.py is the entry script, so Streamlit puts app/ on
	@# sys.path, which is how the pages import `common`.
	$(VENV)/bin/streamlit run app/Home.py --server.port $(PORT)

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
	$(DP) check $(TEAM)
	$(DP) solve $(TEAM) --json /tmp/dancepartner-out.json
	$(DP) explain $(TEAM) /tmp/dancepartner-out.json --dancer $(DANCER)

clean: ## Remove caches and build artefacts
	rm -rf .mypy_cache .pytest_cache .ruff_cache .coverage htmlcov dist build
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
