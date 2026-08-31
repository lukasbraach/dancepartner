# CLAUDE.md — working rules for `dancepartner`

`SPEC.md` is the contract. This file is the short version plus the decisions taken since.

## Milestones — stop and wait

Work milestone by milestone (`SPEC.md` §13) and **stop after each one for review**. Do not
start the next milestone without explicit confirmation.

* **M1 — Core** ✅ `model.py`, `feasibility.py`, `scoring.py`, `solver.py`, full test suite,
  `WEIGHTED_SUM` + `MAXIMIN_THEN_SUM`.
* **M2 — CLI + storage** `storage.py`, `cli.py`, `data/team.example.yaml`, CI workflow.
* **M3 — Remaining objectives** `LEXIMIN`, `LEXICOGRAPHIC_TIERS`, solution enumeration and
  deduplication (`Solution.signature` is already there), `explain` output.
* **M4 — Streamlit UI** all four pages, `i18n.py`.
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
* Until `i18n.py` exists, the only German in the core is `feasibility._MESSAGES`, marked for
  extraction.

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
* Import direction inside the core: `model` ← `feasibility` ← `scoring` ← `solver`.
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

## Commands

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/ruff format . && .venv/bin/ruff check .
.venv/bin/mypy
.venv/bin/python -m pytest --cov=src/dancepartner --cov-report=term-missing --cov-fail-under=90
.venv/bin/pre-commit install
```

Never run `ruff format` without the `*.md` exclude in `pyproject.toml` — ruff reformats fenced
Python blocks in Markdown, and `SPEC.md` is not ours to reformat.
