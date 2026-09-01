# AGENTS.md — working rules for `dancepartner`

Assigns dancers of a Latin formation team to 8 positions with OR-Tools CP-SAT.
**`SPEC.md` is the contract** — vocabulary (§3), hard constraints (§6), and the design decisions
behind the solver (§8), storage (§9), UI (§10), CLI (§11) and tests (§12). Read the section you
are about to touch; this file only lists the rules that bite fastest.

## Language policy

* Code identifiers, comments, docstrings, commit messages, tests, log output, and the on-disk
  YAML/JSON vocabulary: **English**. No exceptions (SPEC §2).
* All user-facing strings in the CLI and the Streamlit UI: **bilingual — English (default) and
  German** — routed through `i18n.py` (English keys, one value table per language, identical key
  sets and placeholders). Selected by `DANCEPARTNER_LANG=en|de` (read once at import; Typer help
  freezes then) or the UI sidebar toggle. Never inline a user-facing literal, in either language,
  in a widget call or a `print`.

## Hard rules

* `src/dancepartner/` never imports `streamlit`. The UI (`app/`) depends on the core, never the
  reverse; `streamlit` stays an extra, not a runtime dependency.
* Only `solver.py` and `cli.py` may import `ortools` and `typer`. `__init__.py` re-exports the
  three solver names lazily (PEP 562 `__getattr__`) — **never make that import eager.** Importing
  any submodule runs `__init__`, so an eager one would drag CP-SAT into the browser build, which
  has no WebAssembly wheel for it, and `dancepartner.model` would stop importing there entirely
  (SPEC §14.2). Nothing in `app/` imports `dancepartner.solver` at module level either; it goes
  behind `common.SOLVER_AVAILABLE`. `tests/test_wasm_deps.py` and the `wasm-parity` CI job
  enforce both.
* Positions are labelled A–H, never 1–8. They are unordered and interchangeable.
* Preferences are directed — never symmetrise. Hard vetoes are the one symmetric exception.
* Integer arithmetic only in the objective (`SolverConfig.score_scale` exists so halving never
  rounds).
* Ask before changing SPEC §3 (glossary) or §6 (hard constraints) — those are what the team
  actually agreed on.
* No dead code kept "for later": no heuristic fallback, no unused weight scheme.

## Environment

`pip` + stdlib `venv` on Python **3.11** (`uv` is not installed on this machine).
`requirements-dev.txt` is the lock file.

## Commands

```bash
make install      # venv + '.[dev]' + pre-commit hooks
make check        # everything CI runs: ruff, mypy --strict, pytest + coverage, CLI smoke test
make ui           # Streamlit UI       (make ui PORT=8600)
make cli          # check/solve/explain (make cli TEAM=data/team.yaml DANCER=lukas-b)

make wasm-serve   # build the browser bundle and serve it on :8000 (editor-only, no solver)
make wasm         # just build it, into wasm/dist, for the GitHub Pages base path
make docker-build # the server image
make docker-up    # app + Caddy from docker/compose.yaml (needs docker/.env)
```

Deployment lives in `wasm/` (the stlite bundle for GitHub Pages) and `docker/` (the server image
and its reverse proxy) — see SPEC §14. Note `wasm/`, not `build/`: `.gitignore` swallows `build/`
and `dist/`, which is also why the bundle is written to `wasm/dist/`.

A new runtime dependency goes in **two** places, or is documented as server-only: `pyproject.toml`
plus `requirements-dev.txt`, and then either `wasm/requirements-wasm.txt` — pinned to exactly the
version the Pyodide index carries — or the `ortools` treatment in SPEC §14.7.

`make` on its own lists all targets. The CLI is the reference interface:

```bash
.venv/bin/dancepartner check   data/team.example.yaml
.venv/bin/dancepartner solve   data/team.example.yaml --top 3 --json out.json
.venv/bin/dancepartner explain data/team.example.yaml out.json --dancer lukas-b
```

## Testing

* Every solver test calls `tests/helpers.py::assert_result_valid` — it re-checks the hard
  constraints *and* the reported stage values, which is the only way to catch a mis-modelled
  objective (SPEC §12).
* Coverage gate: 90 % on `src/dancepartner/`; the suite currently sits at 100 %. Don't lower it
  by accident.
* Performance figures in the README come from real runs on this machine. Re-measure
  (`make cli TEAM=data/team.large.example.yaml DANCER=carolin-r`); never adjust a number by hand.

## Gotchas

* Never run `ruff format` without the `*.md` exclude in `pyproject.toml` — ruff reformats fenced
  Python blocks in Markdown.
* `storage.py` writes canonical YAML with `sort_keys=False` and a fixed key order; never let
  PyYAML sort keys. Dancer order is significant (it defines the position labels).
* The UI saves the coach's *file* only on an explicit button, never autosave — PyYAML drops
  comments on save. It does keep a **draft** (browser IndexedDB, or server RAM keyed by
  `?draft=`) so a reload does not cost an evening of survey entry. A draft is not a save: it
  touches no file of the coach's and never clears the unsaved-changes warning. See
  `app/persistence.py` and SPEC §14.4.
* `wasm/build_static.py` is the third consumer of the `i18n.py` tables — the browser shell renders
  before Python exists, so its loading message is baked in at build time. Both key-scanner tests
  glob it alongside `app/`.
* `data/team.yaml` is gitignored. Never commit real survey data; only the example files are
  tracked.
* `CLAUDE.md` is a symlink to this file — edit `AGENTS.md`.
