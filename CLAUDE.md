# CLAUDE.md — working rules for `dancepartner`

`SPEC.md` is the contract. This file is the short version plus the decisions taken since.

## Milestones — stop and wait

Work milestone by milestone (`SPEC.md` §13) and **stop after each one for review**. Do not
start the next milestone without explicit confirmation.

* **M1 — Core** ✅ `model.py`, `feasibility.py`, `scoring.py`, `solver.py`, full test suite,
  `WEIGHTED_SUM` + `MAXIMIN_THEN_SUM`.
* **M2 — CLI + storage** ✅ `storage.py`, `cli.py`, `i18n.py`, `data/team.example.yaml`,
  `.github/workflows/ci.yml`.
* **M3 — Remaining objectives** `LEXIMIN`, `LEXICOGRAPHIC_TIERS`, solution enumeration and
  deduplication (`Solution.signature` is already there), `explain` output.
* **M4 — Streamlit UI** all four pages (`i18n.py` already exists; add the UI keys).
* **M5 — Polish** German README with a worked example, screenshots, performance notes.

## Language policy (§2)

* Code identifiers, comments, docstrings, commit messages, tests, log output: **English**.
* **Exception — domain terms of art**, used verbatim as identifiers, each with an English
  explanation in its docstring: `Role.HERR` / `Role.DAME`, `has_startanspruch`,
  `needs_coaching`, `wunsch_tiers`, `nicht_wunsch_tiers`, `is_doubled`, `Survey`
  (Teambefragung), `Assignment` / `Solution` (Verpartnerung).
* Do **not** translate these "for readability". `has_startanspruch` is correct;
  `has_starting_claim` invents a term the team does not use.
* All user-facing strings in the Streamlit UI and the CLI: **German**, routed through
  `i18n.py` (M4). Never inline German literals in widget calls.
* `i18n.py` landed in M2 rather than M4, because §2 requires the CLI's German to be routed
  through it and the CLI ships in M2. `feasibility`'s diagnostics moved there too, keyed
  `feasibility.<CODE>`. `test_cli.py::test_no_string_key_is_missing_from_i18n` fails on a key
  that nothing references.

## Glossary (§3 — do not change without asking)

| German | Identifier | Meaning |
|---|---|---|
| Herr / Dame | `Role.HERR`, `Role.DAME` | The two dance roles. Fixed per dancer. |
| Position | index `p`, label A–H | One of the 8 slots. **Unordered and interchangeable.** |
| Doppelbesetzung | `is_doubled` | A position holding two Herren *and* two Damen. |
| Startanspruch | `has_startanspruch` | Must **not** share their position with a same-role dancer. |
| Coachingbedarf | `needs_coaching` | Must **not** be alone in their role on a position. |
| Wunschpartner | `wunsch_tiers` | Ranked sets of desired partners, tier 1 strongest. |
| Nicht-Wunschpartner | `nicht_wunsch_tiers` | Same structure, undesired. |
| Teambefragung | `Survey` | One dancer's complete answers. |
| Verpartnerung | `Assignment` / `Solution` | A complete mapping of dancers to positions. |

Ask before changing anything in §3 or §6 of `SPEC.md` — the glossary and the hard constraints
are the parts the team has actually agreed on.

## Architecture

* `src/dancepartner/` has **zero** imports of `streamlit`. The UI depends on the core, never
  the reverse. A reviewer must be able to delete `app/` and still run everything from the CLI.
* Import direction inside the core: `i18n` ← `model` ← `feasibility` ← `scoring` ← `solver`
  ← `storage`/`cli`. Nothing in `model`/`scoring`/`solver` imports `storage` or `cli`.
* Positions are labelled **A–H, never 1–8**. Numbering invites the team to read a ranking into
  the result that does not exist.
* Preferences are **directed**. A wishing for B does not imply B wishing for A. Never
  symmetrise. (Hard *vetoes* are the one exception and are symmetric by construction — a pair
  either shares a position or does not.)
* Integer arithmetic only in the objective. `SolverConfig.score_scale` is the ×2 factor that
  lets the normalisation halve a score without rounding.

## Decisions taken beyond the spec

* **Environment: `pip` + stdlib `venv` on Python 3.11**, not `uv` on 3.12 (`uv` is not
  installed on the dev machine). `requirements-dev.txt` is the lock file.
* **Doppelbesetzung is independent per role.** The roster has more Damen than Herren, so a
  position may hold 2 Herren and 1 Dame. Hard constraints are per role (`1 ≤ count ≤ 2`);
  coupling the two (2 Herren ⇔ 2 Damen, i.e. two full couples) is a **soft** preference,
  `SolverConfig.prefer_coupled`, implemented as the **weakest objective stage** so it can never
  cost a fulfilled wish. `abs(n_herren - n_damen)` is a lower bound on the lopsided count, not
  an attainable target: normalisation pushes the other way (a granted wish is worth more when
  the position holds a single dancer of the opposite role), so on survey-rich instances the
  stage settles above that bound. Wishes first is the intended trade.
* **Normalisation is driven by the opposite-role count.** What doubles a dancer's cross-role
  contributions is the number of dancers of the *other* role on their position, not their own
  role's count. See `solver._partner_doubled`.
* **`OnlyEnforceIf` instead of `AddMultiplicationEquality`** for the halving (§8 suggests the
  product). The factor is binary, so two enforced linear equalities are exactly equivalent and
  stay linear, which CP-SAT propagates far better.
* **ortools snake_case API** (`model.add_bool_and`, `.negated()`), not the CamelCase used in the
  spec's snippets. The CamelCase aliases are absent from ortools' own type stubs and would
  break `mypy --strict`.
* Dead code is not kept "for later". No heuristic fallback, no unused weight scheme.

## Storage and CLI

* `storage.py` writes canonical YAML with `sort_keys=False` and a fixed key order; **never**
  let PyYAML sort keys, it shuffles `id`/`name`/`role` on every save. Dancer order is preserved
  because symmetry breaking numbers positions by the Herren's input index.
* Tiers are stored as `rank: [ids]` mappings, emitted inline (`1: [anna-b, lena-f]`). False
  flags and empty survey directions are omitted.
* PyYAML cannot preserve comments, so `save_team` drops them. `load_team` never writes, and the
  CLI only writes when asked. The M4 UI must save explicitly, never on autosave.
* `StorageError` means the YAML *shape* is wrong; `ValidationError` means a §6 domain rule
  broke. The CLI maps both to German messages and exit code 1.
* CLI enum options are spelled with hyphens (`--objective maximin-then-sum`, per §11) via the
  `ObjectiveChoice`/`WeightChoice`/`ScopeChoice` enums in `cli.py`, mapped to the domain enums
  by member name. The domain enums keep snake_case values because YAML and JSON carry those.
* `--veto-tier 0` is the CLI spelling of `SolverConfig.veto_tier=None`.
* Exit codes: `0` success, `1` file or instance rejected, `2` bad invocation (typer's), `3` the
  solver found no solution within its limits.
* `solve --json` writes `{"config": ..., "result": ...}`; `explain` reads that back. Keep both
  ends in step — `test_explain_matches_the_solve_table` compares their rendered output.

## Testing rules (§12)

* `tests/helpers.py::assert_result_valid(result, team, config)` is called in **every** solver
  test. It re-checks every hard constraint against the returned assignment *and* compares the
  model's own stage values against an independent recomputation.
* `assert_valid` alone cannot catch a mis-modelled objective — it recomputes scores from the
  assignment, so they stay correct even when CP-SAT optimised something else. Only the stage
  values expose that. This is why `test_reification_cannot_erase_dislike` asserts on
  `result.stages`, not on `per_dancer`.
* Micro-instances (3 positions, 6–9 dancers) with a hand-computed optimum, asserted **by
  value**. `tests/builders.py` has the terse constructors.
* Verify the two constraints the spec singles out by mutation: delete the `add_bool_or` half of
  the reification, or the symmetry-breaking constraint, and the suite must go red.
* Coverage is at 100 % on `src/dancepartner/`; the gate is 90 %.
* `tests/test_cli.py::COUNTING_CLEAN_BUT_INFEASIBLE` is the instance that passes every counting
  check and is still INFEASIBLE. It is the executable form of `feasibility.py`'s "necessary,
  not sufficient" claim — do not "fix" the pre-check to catch it, that needs general matching.

## Commands

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/ruff format . && .venv/bin/ruff check .
.venv/bin/mypy
.venv/bin/python -m pytest --cov=src/dancepartner --cov-report=term-missing --cov-fail-under=90
.venv/bin/pre-commit install

# The CLI is the reference interface.
.venv/bin/dancepartner check   data/team.example.yaml
.venv/bin/dancepartner solve   data/team.example.yaml --objective maximin-then-sum --json out.json
.venv/bin/dancepartner explain data/team.example.yaml out.json --dancer lukas-b
```

CI (`.github/workflows/ci.yml`) installs from `requirements-dev.txt`, then runs ruff, mypy,
pytest with the coverage gate, and the three CLI commands above as a smoke test.

Never run `ruff format` without the `*.md` exclude in `pyproject.toml` — ruff reformats fenced
Python blocks in Markdown, and `SPEC.md` is not ours to reformat.
