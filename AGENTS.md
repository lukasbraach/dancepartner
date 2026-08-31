# AGENTS.md — working rules for `dancepartner`

Assigns dancers of a Latin formation team to 8 positions with OR-Tools CP-SAT.
**`SPEC.md` is the contract** — vocabulary (§3), hard constraints (§6), and the design decisions
behind the solver (§8), storage (§9), UI (§10), CLI (§11) and tests (§12). Read the section you
are about to touch; this file only lists the rules that bite fastest.

## Language policy

* Code identifiers, comments, docstrings, commit messages, tests, log output, and the on-disk
  YAML/JSON vocabulary: **English**. No exceptions (SPEC §2).
* All user-facing strings in the CLI and the Streamlit UI: **German**, routed through `i18n.py`
  (English keys, German values). Never inline a German literal in a widget call or a `print`.

## Hard rules

* `src/dancepartner/` never imports `streamlit`. The UI (`app/`) depends on the core, never the
  reverse; `streamlit` stays an extra, not a runtime dependency.
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
```

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
* The UI saves only on an explicit button, never autosave — PyYAML drops comments on save.
* `data/team.yaml` is gitignored. Never commit real survey data; only the example files are
  tracked.
* `CLAUDE.md` is a symlink to this file — edit `AGENTS.md`.
