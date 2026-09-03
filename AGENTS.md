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
* Two solver backends, one model: `cpsat.py` (ortools) and `highs.py` (highspy, the only one
  with a WebAssembly wheel, so the browser uses it). `solver.py` dispatches and **imports
  neither**; `results.py` holds what they share. Only `cpsat.py`/`cli.py` may import
  `ortools`/`typer`, only `highs.py` and `_milp.py` may import `highspy`.
* `__init__.py` re-exports `solve` lazily (PEP 562 `__getattr__`) — **never make that eager.**
  Importing any submodule runs `__init__`, so an eager backend import would drag CP-SAT into the
  browser build and `dancepartner.model` would stop importing there (SPEC §14.2). `app/` may
  import `dancepartner.solver` at module level but never a backend. `tests/test_wasm_deps.py`
  and the `wasm-parity` CI job enforce it.
* The backends must agree. That is checked by running the **existing** suite against both
  (`pytest --backend=highs`, the `highs-backend` CI job), not by a second set of tests —
  `assert_result_valid` re-derives every constraint independently of the solver. Compare
  **stage value vectors**, never assignments: ties break differently and both are correct.
  `@pytest.mark.cpsat_only` is for tests that measure CP-SAT's own search effort.
* Keep every big-M in `highs.py` at its provable minimum and say why in a comment. An oversized
  M is not a correctness bug, it is a silent performance one — `4 * bound` instead of
  `2 * bound + 1` was the difference between a 4-second solve and a timeout. Better still, no
  M at all when both factors are 0/1: the cross-role halving went from a switch column with
  four big-M rows to an exact AND per term, 368 s → 12 s. `bound` is the largest per-dancer
  weight sum, never the instance-wide one.
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

make wasm-serve   # build the browser bundle and serve it on :8000 (solves with HiGHS)
make wasm         # just build it, into wasm/dist, for the GitHub Pages base path
make docker-build # the server image
make docker-up    # app + Caddy from docker/compose.yaml (needs docker/.env)
```

Deployment lives in `wasm/` (the stlite bundle for GitHub Pages) and `docker/` (the server image
and its reverse proxy) — see SPEC §14. Note `wasm/`, not `build/`: `.gitignore` swallows `build/`
and `dist/`, which is also why the bundle is written to `wasm/dist/`.

A new runtime dependency goes in **two** places, or is documented as server-only: `pyproject.toml`
plus `requirements-dev.txt`, and then either `wasm/requirements-wasm.txt` — pinned to exactly the
version the Pyodide index carries — or the `ortools` treatment in SPEC §14.9.

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
* Loads mint a new draft version, edits overwrite the current one — `set_team(..., new_draft=True)`
  on the three load paths in `common.render_load_controls` only (sidebar and Home). The solver
  settings ride beside the draft as a JSON sidecar (`persistence.save_config`), never inside the
  team YAML. The history is a list in the sidebar, **not** the browser back button: `st.query_params` reports the newest value after a back press in a `st.navigation` app
  (streamlit#13963) and `st.context.url` carries no query string at all. Both verified in a
  browser; don't re-litigate it without re-testing.
* The browser build has three things that are not obvious and are all verified in Chrome, not
  reasoned about (SPEC §14.7, §14.8). **The boot overlay lives outside `#root`** — stlite replaces
  `#root`'s children within a second and takes over with its own progress text — and comes down on
  *content inside* `[data-testid="stMain"]`, never on the containers, which appear empty almost
  immediately. **Python cannot see the URL path**: under stlite `st.context.url` is the bare origin,
  so the shell copies the path into `?page=` for `common.initial_page`. **There is no
  `localStorage`**: Python runs in a Web Worker, which has none — the language preference goes on
  the IDBFS mount beside the drafts.
* A banner drawn immediately before the solve is never seen in the browser: under stlite the
  delta reaches the page only when the Pyodide worker's event loop runs, and a run that blocks
  right after writing never lets it. `common.flush_ui()` sleeps 50 ms to yield, and
  `solve_and_store` calls it first thing. Deleting that sleep silently restores the bug — extra
  reruns do **not** substitute for it, ending a run is not a yield.
* Explicit apply everywhere, and unapplied edits survive navigation: the editing pages mirror
  their widgets into `common.PENDING_*` session keys every run and seed them back on mount.
  `st.data_editor` with dynamic rows takes its widget identity from the data fed in, so the Team
  page freezes its input (`ROSTER_BASE`) while mounted — feed it fresh rows and every edit resets.
  The survey picker is seeded through the one-shot `SURVEY_JUMP` key before it is drawn; do not
  rely on a keyed selectbox keeping its value when its formatted options change.
* Nothing bare at module level in `app/Home.py` — Streamlit's magic renders a stray string or
  expression in the entry script straight into the page. Use `#` comments for constants there.
* `wasm/build_static.py` is the third consumer of the `i18n.py` tables — the browser shell renders
  before Python exists, so its loading message is baked in at build time. Both key-scanner tests
  glob it alongside `app/`.
* `data/team.yaml` is gitignored. Never commit real survey data; only the example files are
  tracked.
* `CLAUDE.md` is a symlink to this file — edit `AGENTS.md`.
