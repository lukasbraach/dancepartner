# CLAUDE.md — working rules for `dancepartner`

`SPEC.md` is the contract. This file is the short version plus the decisions taken since.

## Milestones — stop and wait

Work milestone by milestone (`SPEC.md` §13) and **stop after each one for review**. Do not
start the next milestone without explicit confirmation.

* **M1 — Core** ✅ `model.py`, `feasibility.py`, `scoring.py`, `solver.py`, full test suite,
  `WEIGHTED_SUM` + `MAXIMIN_THEN_SUM`.
* **M2 — CLI + storage** ✅ `storage.py`, `cli.py`, `i18n.py`, `data/team.example.yaml`,
  `.github/workflows/ci.yml`.
* **M3 — Remaining objectives** ✅ `LEXIMIN`, `LEXICOGRAPHIC_TIERS`, solution enumeration and
  deduplication, cross-solution `explain` output.
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

## Objectives and staging

* Stages come from a **generator**, not a list: `LEXIMIN` cannot know its later stages until it
  sees the earlier optima. The generator yields a `Stage` and receives the achieved value back
  via `send`, which makes it deterministic given that sequence — and that is the only reason the
  enumeration pass can rebuild the identical stages on a fresh model.
* `LEXIMIN` runs two stages per round: maximise the floor among the dancers still in play, then
  maximise how many escape it. The "in play" indicators are reified from the scores, so the
  solver picks *which* dancers escape while the stage fixes only *how many*. That is what makes
  it a leximin instead of a maximin repeated on an arbitrary set. The rounds pin the entire
  sorted score vector, so `LEXIMIN` needs no `sum` stage and every optimum has the same total.
* `LEXICOGRAPHIC_TIERS` counts fulfilled wishes per tier rather than scoring them, so
  `SolverConfig.weights` does not affect it. §8 specifies only the wish half; the mirror-image
  dislike stages (`nicht_wunsch.tierN`, minimised) are an addition — without them every dislike
  weaker than `veto_tier` would be ignored outright under this objective.
* **`Stage.surrogate`** marks an artificial bound variable (a maximin/leximin floor). Once the
  objective is gone in the enumeration pass such a variable floats free, and CP-SAT would report
  the same assignment once per admissible floor value. Surrogates are pinned to a single value;
  real objectives get an inequality.
* **`Stage.tie_break` + `solver._lock_in`** is the guard that keeps `prefer_coupled` honest.
  `tier_slack` lets tier *k+1* buy from tier *k*; nothing else may spend that epsilon — not the
  coupled tie-break, and not the enumeration pass. `_lock_in` therefore runs twice: before any
  tie-break stage, and once the stage sequence ends. It records `StageResult.locked_at`.
* `locked_at` is a **floor, not a final figure**. The enumeration pass may find something better
  than pass 1 settled for and is free to. Assertions on it must be one-sided.

## Enumeration

* Two passes. Pass 1 optimises the stages on a throwaway model; pass 2 builds a fresh model,
  replays the same stages as *constraints*, drops the objective, and turns on
  `enumerate_all_solutions` with a single worker.
* `max_solutions == 1` skips pass 2 entirely.
* The collector asks for `max_solutions + 1` and reports `truncated` only if it actually got the
  extra one. Setting `truncated` on merely reaching the cap is wrong — the cap and the true
  count can coincide, and the example team's three optima are exactly that case.
* Dedup is by `Solution.signature` (frozenset of frozensets of dancer ids per position). With
  symmetry breaking on it catches nothing; with it off, the same partition arrives once per
  labelling, which is what `test_dedup_survives_symmetry_breaking_being_off` pins down.
* `near_optimal_ratio` computes its slack from `abs(optimum)`, so 0.95 *widens* the band for a
  negative optimum. Taking `0.95 * optimum` literally would tighten it there — the opposite of
  what "near-optimal" means.
* Anything asserting the canonical position numbering must use `max_solutions=1` or check the
  whole shortlist: `_ranking_key` imposes an order of its own and will otherwise mask a missing
  symmetry-breaking constraint.

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
* `--top N` sets `max_solutions` **and** prints all N, each alternative diffed against the best.
  `--near-optimal` and `--tier-slack` expose the other two M3 knobs.
* `explain --solution N` picks a shortlist entry; with more than one solution in the file it also
  summarises how stable the dancer's partners are across the whole shortlist. That is the
  question enumeration exists to answer — a partner in every optimum is not a choice the coach
  has to make, one in three of twenty is.
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
* Verify the load-bearing constraints by mutation; each must turn the suite red:
  the `add_bool_or` half of the reification (35 failures), the symmetry-breaking constraint (3),
  the signature dedup (1), and the `_lock_in` tie-break guard (2).
* Coverage is at 100 % on `src/dancepartner/`; the gate is 90 %.
* `tests/test_objectives.py::divergent_instance` is the instance where maximising the total and
  levelling up genuinely disagree — `MAXIMIN_THEN_SUM` reaches `[0, 0, 2, 6, 6, 6, 6]`, `LEXIMIN`
  gives up five points of total for `[0, 2, 2, 3, 4, 4, 6]`. Without it the two objectives look
  identical on every instance in the repo.
* `assert_leximin_vector` reconstructs the score multiset from the reported rounds alone. If the
  rounds and the assignment disagree, one of them is lying.
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
