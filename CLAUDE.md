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
* **M4 — Streamlit UI** ✅ `app/` with all four pages, the `ui.`/`nav.` i18n keys,
  `reporting.py`, `tests/test_app.py`.
* **M5 — Polish** ✅ German `README.md` with a worked example and measured performance notes,
  `data/team.large.example.yaml`. Screenshots deferred by agreement — the README ships
  without image slots rather than with broken ones.

## Language policy (§2)

* Code identifiers, comments, docstrings, commit messages, tests, log output, **and the on-disk
  YAML/JSON vocabulary**: English. No exceptions — the German terms of art were renamed at the end
  of M3, see §2.1 of `SPEC.md` for the mapping and the reason.
* All user-facing strings in the Streamlit UI and the CLI: **German**, routed through `i18n.py`.
  The dict's *keys* are English, its *values* are German. Never inline a German literal in a widget
  call or a `print`.
* Where an English identifier replaced a German term the team says out loud, the docstring names
  the old word once (`is_pole_position` — formerly *Startanspruch*). That is a breadcrumb, not a
  licence to bring the German spelling back as an identifier.
* `is_pole_position` is a claim on the *starting slot*, not a ranking. Say so in any new docstring
  that mentions it — read as "ranked first" it means the opposite of the constraint it encodes.

## Glossary (§3 — do not change without asking)

| Identifier | Formerly | Meaning |
|---|---|---|
| `Role.LEADER`, `Role.FOLLOWER` | Herr / Dame | The two dance roles. Fixed per dancer. |
| position index `p`, label A–H | Position | One of the 8 slots. **Unordered and interchangeable.** |
| `is_doubled` | Doppelbesetzung | A position holding two leaders *and* two followers. |
| `is_pole_position` | Startanspruch | Must **not** share their position with a same-role dancer. |
| `needs_coaching` | Coachingbedarf | Must **not** be alone in their role on a position. |
| `desired_tiers` | Wunschpartner | Ranked sets of desired partners, tier 1 strongest. |
| `not_desired_tiers` | Nicht-Wunschpartner | Same structure, undesired. |
| `Survey` | Teambefragung | One dancer's complete answers. |
| `Solution` | Verpartnerung | A complete mapping of dancers to positions. |

Ask before changing anything in §3 or §6 of `SPEC.md` — the glossary and the hard constraints are
the parts the team has actually agreed on. The vocabulary rename was agreed that way.

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
* **Doppelbesetzung is independent per role.** The roster has more followers than leaders, so a
  position may hold 2 leaders and 1 follower. Hard constraints are per role (`1 ≤ count ≤ 2`);
  coupling the two (2 leaders ⇔ 2 followers, i.e. two full couples) is a **soft** preference,
  `SolverConfig.prefer_coupled`, implemented as the **weakest objective stage** so it can never
  cost a fulfilled wish. `abs(n_leaders - n_followers)` is a lower bound on the lopsided count, not
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
  dislike stages (`not_desired.tierN`, minimised) are an addition — without them every dislike
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

## The UI (M4)

* `app/` is **not** on the SPEC.md §5 filenames. Two agreed deviations, both recorded in
  `app/Home.py`'s docstring: the page modules are English (`team.py`, `survey.py`,
  `solution.py`, `analysis.py`) with German sidebar titles supplied by `st.navigation` /
  `st.Page(title=de(...))`, and the numeric prefixes are gone. Streamlit derives a file-based
  page's label from its filename, so SPEC's names would have put untranslated German — and an
  umlaut-less "Loesung" — outside `i18n.py`; and `1_Team` is not a valid module name under
  `mypy --strict`. Ordering now comes from the page list, which is the only thing the prefixes
  ever did.
* **`streamlit` is an extra (`ui`), never a runtime dependency.** That is what makes "delete
  `app/` and the CLI still works" enforceable rather than aspirational; CI proves it by moving
  `app/` aside, uninstalling streamlit and running `solve`.
* `app/common.py` holds session state, the cached solve and the formatting. Pages are thin.
* **`st.cache_data` cannot hash a pydantic model.** `cached_solve` passes explicit
  `hash_funcs`: `dump_team` for the `Team`, `model_dump_json()` for the `SolverConfig`. Both
  are the core's own canonical serialisations, so two teams that save identically share an
  entry — which is the intended meaning of "keyed on a hash of `(Team, SolverConfig)`".
* **Never `Team.model_copy` to edit.** It skips validation on a frozen model, which is exactly
  the check being relied on. `common.with_survey` goes through the constructor and returns the
  surveys in roster order so the saved YAML stays stable.
* The feasibility panel passes the **current** `SolverConfig`, not a default one: `veto_tier`
  and `scope` change the verdict. (`cli.py::check` still passes a default — that is a
  pre-existing CLI limitation, not a pattern to copy.)
* Editing pages validate SPEC §6 rules 3 and 4 **themselves** so the conflict reads in German.
  Pydantic stays the final gate, but its message is English and must never reach the coach.
* Empty and orphaned tiers are renumbered, not rejected: browser editing breaks the
  "contiguous from 1" rule constantly, and the coach did not cause it. See
  `common.renumber_tiers` / `tiers_from_selections`.
* Colour encodes satisfaction only — never name, never role. `common.score_badge` scales
  against the achieved range of the solution being shown, not an absolute.
* `st.data_editor` is fed `list[dict]`, not a DataFrame: SPEC §4 keeps pandas out unless a
  milestone needs it, and dicts round-trip fine.

## `reporting.py`

`unfulfilled_desired` / `respected_not_desired` were extracted from `cli.py::_explain_dancer`
because the UI needs the same numbers and duplicating them would put scope-dependent logic
outside the covered core. Note the asymmetry, which is deliberate: **`respected_not_desired`
filters by `config.scope`, `unfulfilled_desired` does not.** Claiming credit for keeping two
leaders apart under `CROSS_ROLE_ONLY` would be claiming credit for a constraint nothing
enforced; a wish the coach wrote down, by contrast, stays visibly missed whether or not the
objective ever scored it.

The extraction must leave CLI output **byte-identical** — `test_explain_matches_the_solve_table`
and the determinism tests are the guard.

## Testing the UI

* `tests/test_app.py` drives `streamlit.testing.v1.AppTest` in-process; the coverage gate stays
  on `src/` only.
* `tests/conftest.py` puts `app/` on `sys.path`, reproducing what `streamlit run app/Home.py`
  does. Without it, a page test passes only when a `Home.py` test happened to run first.
* Address widgets by **key**, not index (`_tier_widgets`): an index is wrong the moment a
  dancer has a second stored tier.
* `st.dataframe(...).value` comes back as a DataFrame, not the list that was passed in.
* Widget state is read-only in place — assign a whole new dict to the session-state key.
* `test_the_ui_inlines_no_german_literal` scans `app/` for umlauts outside docstrings, and
  `test_no_string_key_is_missing_from_i18n` now globs `app/` too, so a UI-only key is not
  reported unused. Keys looked up dynamically need a prefix in `dynamic_prefixes`.

## Performance and the example instances

* `data/team.example.yaml` (20 dancers) and `data/team.large.example.yaml` (24, tiers to 3)
  are both committed and both used by the README's numbers. `make cli TEAM=... DANCER=...`
  reruns them.
* **`SolveResult.wall_time` used to report only the last stage.** A `CpSolver` reports its most
  recent solve, and `_run_stages` solves once per stage; reading `solver.wall_time` after the
  loop under-reported the 24-dancer instance as 2.4 s when it took 12.3 s. `_run_stages` now
  accumulates and returns the totals. `test_wall_time_counts_every_stage_not_just_the_last`
  pins it with a spy on `_make_solver` and fails if the accumulation is reverted.
* **Counter-intuitive but measured: `LEXIMIN` is ~70× *faster* than `WEIGHTED_SUM`** on the
  24-dancer instance (0.17 s vs 12.5 s), and both reach the same total. Optimising a bare sum
  leaves a huge space in which to prove no better assignment exists; leximin's rounds pin the
  whole sorted score vector, and each of those constraints prunes hard. Do not "optimise" the
  staging on the assumption that more stages cost more time — measure.
* On the 20-dancer instance every objective finishes under 0.1 s, so the choice is about
  meaning, not speed. Enumeration is nearly free (`--top 50` costs < 0.2 s over `--top 1`):
  pass 2 runs on a model whose optima are already pinned.
* Any figure quoted in the README came from an actual run on this machine. Re-measure rather
  than adjusting a number by hand.

## Storage and CLI

* `storage.py` writes canonical YAML with `sort_keys=False` and a fixed key order; **never**
  let PyYAML sort keys, it shuffles `id`/`name`/`role` on every save. Dancer order is preserved
  because symmetry breaking numbers positions by the leaders' input index.
* Tiers are stored as `rank: [ids]` mappings under `desired:` / `not_desired:`, emitted inline
  (`1: [anna-b, lena-f]`). False
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
* Synthetic test dancers are `led0..`/`fol0..` (see `tests/builders.py::roster`). Roster order is
  significant — symmetry breaking numbers positions by leader input index — so those ids double as
  the canonical ordering.
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

# The UI. Run it from the repository root -- the pages import `common` from app/, which
# Streamlit puts on sys.path because Home.py is the entry script.
.venv/bin/pip install -e '.[dev]'      # or '.[ui]' for the UI alone
.venv/bin/streamlit run app/Home.py
```

The `Makefile` wraps all of the above; `make` on its own lists the targets.

```bash
make install      # venv + '.[dev]' + pre-commit hooks
make ui           # the Streamlit UI      (make ui PORT=8600)
make check        # everything CI runs: lint, typecheck, cov, cli
make cli          # check/solve/explain   (make cli TEAM=data/team.yaml)
```

`.streamlit/config.toml` is committed and sets `server.headless`. Without it Streamlit's first
run stops at an interactive `Email:` prompt, which hangs `make ui` on a fresh clone; it also
turns off `gatherUsageStats`, because this app handles a team's survey answers.

CI (`.github/workflows/ci.yml`) installs from `requirements-dev.txt`, then runs ruff, mypy,
pytest with the coverage gate, and the three CLI commands above as a smoke test.

Never run `ruff format` without the `*.md` exclude in `pyproject.toml` — ruff reformats fenced
Python blocks in Markdown, and `SPEC.md` is not ours to reformat.
