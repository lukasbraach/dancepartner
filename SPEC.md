# `dancepartner` — Specification

This is the contract for the shipped system: the domain vocabulary, the hard constraints, and the
design decisions behind the solver, the CLI and the UI. It describes what exists. The working
rules for contributors and agents live in `AGENTS.md`; section numbers here (§2, §6, §8, …) are
referenced from docstrings throughout the codebase, so they stay stable.

---

## 1. Context

We assign dancers of a Latin formation team (Lateinformation, VfL Pinneberg) to **8 unordered
positions**. Each position is occupied by at least one leader and at least one follower,
optionally two per role (*Doppelbesetzung* — two couples share a position and alternate across
tournaments).

The team runs an internal survey (*Teambefragung*) in which every dancer names desired and
undesired partners in ranked tiers. The assignment is a constraint optimisation problem, solved
exactly with OR-Tools CP-SAT.

The final human decision stays with the coach — the tool produces a **shortlist of optimal and
near-optimal assignments**, never a single mandated answer.

---

## 2. Language policy

* **All code identifiers, comments, docstrings, commit messages, tests and log output: English.**
  No exceptions, including the domain terms of art — see §3 for the mapping.
* **The on-disk YAML and JSON use the same English vocabulary as the code.** `role: leader`,
  `desired:`, `not_desired:`, `is_pole_position:`. There is one vocabulary, not two.
* **All user-facing strings in the Streamlit UI and the CLI: German.** They route through
  `dancepartner/i18n.py`, a flat `dict[str, str]` with English keys and German values. Never
  inline a German string literal in a widget call or a `print`.
* Where an English identifier replaced a German term the team actually says, its docstring names
  the old term once (`is_pole_position` — formerly *Startanspruch*). That is a breadcrumb for
  readers who know the team's vocabulary, not a licence to reintroduce the German spelling as an
  identifier.

### 2.1 History

Until the end of Milestone 3 this section mandated the German nouns verbatim as identifiers
(`has_startanspruch`, `Role.HERR`). That produced a codebase in two languages, with the seam
running through the data model, the storage format and the test suite, so the team agreed to move
to the English `leader`/`follower` vocabulary the wider dance world uses. There is **no backwards
compatibility**: a team file in the old vocabulary fails to load with a `StorageError` naming the
offending key. The mapping, kept as the migration aid for private team files:

| Was | Is now |
|---|---|
| `Role.HERR` / `"herr"` | `Role.LEADER` / `"leader"` |
| `Role.DAME` / `"dame"` | `Role.FOLLOWER` / `"follower"` |
| `has_startanspruch` | `is_pole_position` |
| `wunsch_tiers`, YAML `wunsch:` | `desired_tiers`, YAML `desired:` |
| `nicht_wunsch_tiers`, YAML `nicht_wunsch:` | `not_desired_tiers`, YAML `not_desired:` |
| `fulfilled_wunsch` | `fulfilled_desired` |
| `violated_nicht_wunsch` | `violated_not_desired` |
| `PositionAssignment.herren` / `.damen` | `.leaders` / `.followers` |
| `TOO_MANY_STARTANSPRUCH` | `TOO_MANY_POLE_POSITION` |

---

## 3. Glossary (identifier → meaning)

The German column records what the team calls each thing. It keeps the vocabulary shift traceable
— it is **not** a licence to use those spellings as identifiers.

| Identifier | Deutsch | Meaning |
|---|---|---|
| `Role.LEADER`, `Role.FOLLOWER` | Herr / Dame | The two dance roles. Fixed per dancer, not a preference. |
| position index `p`, label A–H | Position | One of the 8 slots on the floor. Unordered and interchangeable in the model. |
| `is_doubled` | Doppelbesetzung | A position holding two leaders *and* two followers. |
| `is_pole_position` | Startanspruch | Dancer must **not** share their position with another dancer of the same role. Hard constraint. A claim on the starting slot, **not** a ranking — read as "ranked first" it means the opposite of the constraint it encodes. |
| `needs_coaching` | Coachingbedarf | Dancer must **not** be the only one of their role on a position. Hard constraint. |
| `desired_tiers` | Wunschpartner | Ranked list of sets of desired partners. Tier 1 = strongest wish. Sets within a tier are equivalent. |
| `not_desired_tiers` | Nicht-Wunschpartner | Same structure, for undesired partners. |
| `Survey` | Teambefragung | One dancer's complete set of answers. |
| `Solution` | Verpartnerung | A complete mapping of dancers to positions. |

Dancers not named in any tier are **neutral**: assignable, contributing zero to that dancer's
score.

---

## 4. Tech stack

* Python **3.11**, `pip` + stdlib `venv` (`uv` is not installed on the dev machine).
  `requirements-dev.txt` is the lock file.
* `ortools` (CP-SAT) — solver. The **snake_case API** (`model.add_bool_and`, `.negated()`), not
  the CamelCase aliases: those are absent from ortools' own type stubs and break `mypy --strict`.
* `pydantic` v2 — data model and validation.
* `streamlit` — UI, as the **`ui` extra**, never a runtime dependency.
* `typer` — CLI.
* `pyyaml` — persistence.
* Dev: `pytest`, `pytest-cov`, `ruff` (lint + format), `mypy --strict`, `pre-commit`.
* CI: GitHub Actions running ruff, mypy, pytest with the coverage gate, and the three CLI commands
  as a smoke test.

No Jupyter notebooks. No pandas.

---

## 5. Repository layout

```
dancepartner/
├── pyproject.toml
├── requirements-dev.txt
├── Makefile
├── SPEC.md
├── AGENTS.md            # CLAUDE.md is a symlink to it
├── data/
│   ├── team.example.yaml         # 20 dancers, tiers to 2
│   └── team.large.example.yaml   # 24 dancers, tiers to 3
├── src/dancepartner/
│   ├── __init__.py
│   ├── model.py         # pydantic domain model
│   ├── feasibility.py   # cheap counting pre-checks
│   ├── scoring.py       # weight schemes, per-dancer satisfaction reporting
│   ├── solver.py        # CP-SAT model construction + staged optimisation
│   ├── reporting.py     # scope-aware satisfaction numbers shared by CLI and UI
│   ├── storage.py       # YAML load/save
│   ├── i18n.py          # German UI strings
│   └── cli.py
├── app/
│   ├── Home.py
│   ├── common.py        # session state, cached solve, formatting; pages are thin
│   └── pages/
│       ├── team.py
│       ├── survey.py
│       ├── solution.py
│       └── analysis.py
└── tests/
```

`src/dancepartner` has **zero** imports of `streamlit`. The UI depends on the core, never the
reverse — deleting `app/` leaves everything runnable from the CLI, and CI proves it (§10). Import
direction inside the core: `i18n` ← `model` ← `feasibility` ← `scoring` ← `solver` ←
`storage`/`cli`.

The page modules are English with German sidebar titles supplied via `st.navigation` /
`st.Page(title=de(...))`: Streamlit derives a file-based page's label from its filename, which
would put untranslated German outside `i18n.py`, and a numeric prefix like `1_Team` is not a valid
module name under `mypy --strict`. Ordering comes from the page list.

---

## 6. Data model (`model.py`)

```python
class Role(StrEnum):
    LEADER = "leader"
    FOLLOWER = "follower"

class Dancer(BaseModel):
    id: str                      # stable slug, e.g. "lukas-b"
    name: str
    role: Role
    is_pole_position: bool = False    # must be alone in their role on the position
    needs_coaching: bool = False      # must NOT be alone in their role on the position

class Tier(BaseModel):
    rank: int                    # 1 = strongest preference
    dancer_ids: frozenset[str]   # equivalent options within the tier

class Survey(BaseModel):
    dancer_id: str
    desired_tiers: list[Tier] = []
    not_desired_tiers: list[Tier] = []

class Team(BaseModel):
    dancers: list[Dancer]
    surveys: list[Survey] = []
    n_positions: int = 8
```

Validators, all of which raise on violation:

1. `is_pole_position` and `needs_coaching` are mutually exclusive per dancer.
2. Tier ranks are contiguous starting at 1, no duplicates.
3. A dancer id appears in at most one tier per direction (no dancer both tier-1 and tier-3 wish).
4. A dancer id appears in **at most one direction** — being both wished and un-wished is a survey
   entry error, not a subtle preference.
5. No self-references.
6. All referenced ids exist in `dancers`.
7. Every dancer has at most one `Survey`.

**Preferences are directed.** A wishing for B does not imply B wishing for A. Both directions are
scored independently and are never silently symmetrised. (Hard *vetoes*, §8, are the one symmetric
exception — a pair either shares a position or does not, by construction.)

Preferences are about *cross-role* partners by default (a leader names followers), but same-role
entries matter too: on a Doppelbesetzung two leaders share a position and their working
relationship counts. `PreferenceScope` selects `CROSS_ROLE_ONLY` (default) or `ALL`; same-role
preferences are scored only when both dancers share a position.

---

## 7. Feasibility pre-check (`feasibility.py`)

Runs before the CP-SAT model is built and returns structured, German-readable diagnostics, so the
solver never returns a bare INFEASIBLE for a cause that is decidable by counting.

With `n = len(leaders)` and 8 positions:

* Exactly `n - 8` positions carry two leaders, exactly `16 - n` carry a single leader.
* Therefore: `count(is_pole_position ∧ LEADER) ≤ 16 - n`
* And: `n - 8 ≥ ceil(count(needs_coaching ∧ LEADER) / 2)`
* And: `8 ≤ n ≤ 16`

Identical checks for followers, plus a check for hard vetoes (§8) making a role infeasible. Each
failure is a `FeasibilityIssue(code, message_de, involved_ids)` the UI can surface.

These checks are **necessary, not sufficient** — they find real obstacles but prove no
solvability. `tests/test_cli.py::COUNTING_CLEAN_BUT_INFEASIBLE` is the executable form of that
claim: an instance that passes every counting check and is still INFEASIBLE. Do not "fix" the
pre-check to catch it; that needs general matching, which is the solver's job.

---

## 8. Solver (`solver.py`)

### Variables

* `x[d, p] ∈ {0,1}` — dancer `d` on position `p`.
* `together[d, e]` — reified, true iff `d` and `e` share a position.

### Hard constraints

1. `add_exactly_one(x[d, p] for p in positions)` for every dancer.
2. Per position and **per role**: `1 ≤ Σ x ≤ 2`. The bounds are independent per role — the roster
   rarely has equal counts, so a position may hold 2 leaders and 1 follower. Coupling the two
   (2 leaders ⇔ 2 followers, two full couples) is the **soft** `prefer_coupled` stage below, never
   a hard constraint.
3. Pole position: `add(role_count == 1).only_enforce_if(x[d, p])`.
4. Coaching need: `add(role_count >= 2).only_enforce_if(x[d, p])`.
5. Optional hard veto: if `SolverConfig.veto_tier` is set (default `1`), all `not_desired` entries
   at that tier or stronger get `together[d, e] == 0`.

### Reification — both directions are mandatory

```python
b = model.new_bool_var("")
model.add_bool_and([x[d, p], x[e, p]]).only_enforce_if(b)
model.add_bool_or([x[d, p].negated(), x[e, p].negated()]).only_enforce_if(b.negated())
```

With only the first implication and negative weights present, the solver sets `b = 0` for a pair
that actually shares a position and erases the dislike penalty.
`test_reification_cannot_erase_dislike` pins this — on `result.stages`, not `per_dancer`, because
recomputed scores stay correct even when CP-SAT optimised something else (§12).

### Symmetry breaking

Positions are unordered — without symmetry breaking the search space is inflated by 8! = 40320.
A canonical numbering over leaders, ordered by their index in the input list:

```
x[leader_i, p] <= Σ_{j<i} x[leader_j, p-1]     for p >= 1
```

This is also why dancer input order is significant: it defines the canonical position labels.

### Scoring (`scoring.py`)

`score[d] = Σ_e weight(d, e) * together[d, e]`, integer arithmetic only.

Weight schemes, selectable via `SolverConfig.weights`:

* `LINEAR` — tier *k* of *K* is worth `K - k + 1`, dislikes negative and symmetric.
* `GEOMETRIC` — `B^(K-k)` with `B` computed from the instance so that one tier-*k* fulfilment
  outranks all possible tier-*(k+1)* fulfilments. Degrades CP-SAT's bound quality on larger
  instances; the docstring warns about it.

**Normalisation** (`SolverConfig.normalize_double`, default on). A dancer with two cross-role
partners has twice the score contributions; unnormalised, the solver systematically favours
Doppelbesetzungen for well-liked dancers. What doubles a dancer's cross-role contributions is the
number of dancers of the **other** role on their position, not their own role's count — see
`solver._partner_doubled`. Scores live on a ×2-scaled integer scale
(`SolverConfig.score_scale`) so the doubled case halves without rounding. The halving uses two
linear equalities under `only_enforce_if` rather than `add_multiplication_equality`: the factor is
binary, so they are exactly equivalent, stay linear, and propagate far better.

Normalisation also interacts with `prefer_coupled`: a granted wish is worth more when the position
holds a single dancer of the opposite role, so `abs(n_leaders - n_followers)` is only a lower
bound on the lopsided count, not an attainable target. Wishes first is the intended trade.

### Objective staging

`SolverConfig.objective` selects one of:

* `WEIGHTED_SUM` — single-stage `maximize(Σ score)`. Simplest, and reliably leaves one or two
  people with nothing. Kept for comparison.
* `MAXIMIN_THEN_SUM` — **default.** Stage 1 maximises `lo` with `lo ≤ score[d]` for all `d`.
  Stage 2 pins `lo` to its optimum and maximises `Σ score`.
* `LEXIMIN` — two stages per round: maximise the floor among the dancers still in play, then
  maximise how many escape it. The "in play" indicators are reified from the scores, so the solver
  picks *which* dancers escape while the stage fixes only *how many* — that is what makes it a
  leximin instead of a maximin repeated on an arbitrary set. The rounds pin the entire sorted
  score vector, so `LEXIMIN` needs no `sum` stage and every optimum has the same total.
* `LEXICOGRAPHIC_TIERS` — counts fulfilled wishes per tier rather than scoring them, so
  `SolverConfig.weights` does not apply. The mirror-image dislike stages (`not_desired.tierN`,
  minimised) run too — without them every dislike weaker than `veto_tier` would be ignored
  outright. `tier_slack` (ε) lets tier *k+1* buy from tier *k*.

Stages come from a **generator**, not a list: `LEXIMIN` cannot know its later stages until it sees
the earlier optima. The generator yields a `Stage` and receives the achieved value back via
`send`, which makes it deterministic given that sequence — the only reason the enumeration pass
can rebuild the identical stages on a fresh model. Each stage's objective value is logged.

Two `Stage` flags matter for correctness:

* **`Stage.surrogate`** marks an artificial bound variable (a maximin/leximin floor). Once the
  objective is gone in the enumeration pass such a variable floats free, and CP-SAT would report
  the same assignment once per admissible floor value. Surrogates are pinned to a single value;
  real objectives get an inequality.
* **`Stage.tie_break` + `solver._lock_in`** keep `prefer_coupled` honest: `tier_slack` is the only
  thing allowed to spend the inter-tier epsilon — not the coupled tie-break, and not the
  enumeration pass. `_lock_in` runs twice (before any tie-break stage, and once the stage sequence
  ends) and records `StageResult.locked_at`. `locked_at` is a **floor, not a final figure**: the
  enumeration pass may find something better than pass 1 settled for and is free to. Assertions on
  it must be one-sided.

`SolveResult.wall_time` accumulates over **all** stages (`_run_stages` sums per-stage times; a
`CpSolver` only reports its most recent solve).
`test_wall_time_counts_every_stage_not_just_the_last` pins the accumulation.

### Solution enumeration

Preference problems have many equal optima, and the differences between them are exactly the
choices the coach still has. Two passes:

1. Optimise the stages on a throwaway model.
2. Build a fresh model, replay the same stages as *constraints*, drop the objective, and turn on
   `enumerate_all_solutions` with a single worker. `max_solutions == 1` skips this pass entirely.

Details that are easy to get wrong:

* The collector asks for `max_solutions + 1` and reports `truncated` only if it actually got the
  extra one. Setting `truncated` on merely reaching the cap is wrong — the cap and the true count
  can coincide, and the example team's three optima are exactly that case.
* Dedup is by `Solution.signature`, the frozenset of frozensets of dancer ids per position. With
  symmetry breaking on it catches nothing; with it off, the same partition arrives once per
  labelling (`test_dedup_survives_symmetry_breaking_being_off`).
* `near_optimal_ratio` computes its slack from `abs(optimum)`, so 0.95 *widens* the band for a
  negative optimum. Taking `0.95 * optimum` literally would tighten it there — the opposite of
  what "near-optimal" means.

### Result type

```python
class PositionAssignment(BaseModel):
    leaders: list[str]
    followers: list[str]

class Solution(BaseModel):
    positions: list[PositionAssignment]
    total_score: int
    min_score: int
    per_dancer: dict[str, DancerSatisfaction]

class DancerSatisfaction(BaseModel):
    score: int
    fulfilled_desired: dict[int, list[str]]      # tier -> partner ids granted
    violated_not_desired: dict[int, list[str]]
    neutral_partners: list[str]
```

Positions in the output are labelled A–H, not 1–8: the model treats them as interchangeable, and
numbering invites the team to read a ranking into the result that does not exist.

`reporting.py` holds `unfulfilled_desired` / `respected_not_desired`, shared by CLI and UI. The
asymmetry is deliberate: `respected_not_desired` filters by `config.scope`,
`unfulfilled_desired` does not. Claiming credit for keeping two leaders apart under
`CROSS_ROLE_ONLY` would be claiming credit for a constraint nothing enforced; a wish the coach
wrote down stays visibly missed whether or not the objective ever scored it.

---

## 9. Persistence (`storage.py`)

YAML in `data/`, human-editable and diffable. `load_team(path) -> Team`, `save_team(team, path)`.
No database.

* Canonical output: `sort_keys=False` with a fixed key order — PyYAML left to itself shuffles
  `id`/`name`/`role` on every save. Dancer order is preserved (it defines the canonical position
  labels, §8).
* Tiers are stored as `rank: [ids]` mappings under `desired:` / `not_desired:`, emitted inline
  (`1: [anna-b, lena-f]`). False flags and empty survey directions are omitted.
* PyYAML cannot preserve comments, so `save_team` drops them. `load_team` never writes; writing
  happens only on explicit request (CLI flag, UI save button — never autosave).
* `StorageError` means the YAML *shape* is wrong; `ValidationError` means a §6 domain rule broke.
  The CLI maps both to German messages and exit code 1.
* Real survey data never enters the repo: `data/team.yaml` is gitignored, only the two example
  files are tracked.

---

## 10. Streamlit UI (`app/`)

A home page and four working pages, all thin over `app/common.py` (session state, the cached
solve, formatting):

* `Home.py` — load / upload / create a team file, feasibility summary panel (§7), explicit save.
* `pages/team.py` — dancer table with `st.data_editor`: name, role, pole position, coaching need.
* `pages/survey.py` — pick a dancer, then per direction a dynamic list of tiers, each an
  `st.multiselect` over eligible dancers, with add/remove tier buttons.
* `pages/solution.py` — solver config widgets, a run button, the best solution as 8 cards with
  badges for fulfilled wishes and violated dislikes.
* `pages/analysis.py` — per-dancer satisfaction sorted ascending (the unhappiest first — that is
  the row the coach actually needs), plus a browser over the enumerated solutions with a diff
  against the selected one.

Implementation rules:

* Team state lives in `st.session_state`, persisted to YAML **only on explicit save**.
* The solve runs inside `st.spinner`, wrapped in `st.cache_data`. `st.cache_data` cannot hash a
  pydantic model, so `cached_solve` passes explicit `hash_funcs`: `dump_team` for the `Team`,
  `model_dump_json()` for the `SolverConfig` — the core's canonical serialisations, so two teams
  that save identically share an entry. The configured time limit is passed to the solver so the
  UI cannot hang.
* **Never `Team.model_copy` to edit**: it skips validation on a frozen model, which is exactly the
  check being relied on. `common.with_survey` goes through the constructor and returns surveys in
  roster order so the saved YAML stays stable.
* The feasibility panel passes the **current** `SolverConfig`, not a default one — `veto_tier`
  and `scope` change the verdict. (`cli.py::check` still passes a default; that is a pre-existing
  CLI limitation, not a pattern to copy.)
* Editing pages validate §6 rules 3 and 4 **themselves** so the conflict reads in German. Pydantic
  stays the final gate, but its English message must never reach the coach.
* Empty and orphaned tiers are renumbered, not rejected — browser editing breaks the "contiguous
  from 1" rule constantly, and the coach did not cause it. See `common.renumber_tiers` /
  `tiers_from_selections`.
* Colour encodes satisfaction only, never name or role. `common.score_badge` scales against the
  achieved range of the solution being shown, not an absolute.
* `st.data_editor` is fed `list[dict]`, not a DataFrame (§4 keeps pandas out).

`streamlit` being an extra is what makes "delete `app/` and the CLI still works" enforceable
rather than aspirational; CI proves it by moving `app/` aside, uninstalling streamlit and running
`solve`.

---

## 11. CLI (`cli.py`)

The CLI is the reference interface — everything the UI can do, it can do.

```
dancepartner check   data/team.yaml
dancepartner solve   data/team.yaml --objective maximin-then-sum --top 10 --json out.json
dancepartner explain data/team.yaml out.json --dancer lukas-b
```

* Enum options are spelled with hyphens (`--objective maximin-then-sum`) via the
  `ObjectiveChoice`/`WeightChoice`/`ScopeChoice` enums, mapped to the domain enums by member name.
  The domain enums keep snake_case values because YAML and JSON carry those.
* `--veto-tier 0` is the CLI spelling of `SolverConfig.veto_tier=None`.
* `--top N` sets `max_solutions` **and** prints all N, each alternative diffed against the best.
  `--near-optimal` and `--tier-slack` expose the other two enumeration knobs.
* `solve --json` writes `{"config": ..., "result": ...}`; `explain` reads that back. Keep both
  ends in step — `test_explain_matches_the_solve_table` compares their rendered output.
* `explain --solution N` picks a shortlist entry; with more than one solution in the file it also
  summarises how stable the dancer's partners are across the whole shortlist. That is the question
  enumeration exists to answer: a partner in every optimum is not a choice the coach has to make,
  one in 3 of 20 is.
* Exit codes: `0` success, `1` file or instance rejected, `2` bad invocation (typer's), `3` the
  solver found no solution within its limits.

---

## 12. Testing

* `tests/helpers.py::assert_result_valid(result, team, config)` is called in **every** solver
  test. It re-checks every hard constraint against the returned assignment *and* compares the
  model's reported stage values against an independent recomputation. The second half is not
  optional: recomputed scores stay correct even when CP-SAT optimised the wrong thing, so only the
  stage values expose a mis-modelled objective.
* Hand-constructed micro-instances (3 positions, 6–9 dancers) with a known optimum, asserted **by
  value**. `tests/builders.py` has the terse constructors; synthetic dancers are `led0..`/`fol0..`,
  and their roster order doubles as the canonical position ordering (§8).
* The load-bearing constraints are verified by mutation — each of these must turn the suite red:
  the `add_bool_or` half of the reification, the symmetry-breaking constraint, the signature
  dedup, the `_lock_in` tie-break guard.
* `tests/test_objectives.py::divergent_instance` is the instance where maximising the total and
  levelling up genuinely disagree (`MAXIMIN_THEN_SUM` reaches `[0, 0, 2, 6, 6, 6, 6]`, `LEXIMIN`
  gives up five points of total for `[0, 2, 2, 3, 4, 4, 6]`). Without it the two objectives look
  identical on every instance in the repo.
* `assert_leximin_vector` reconstructs the score multiset from the reported rounds alone; if the
  rounds and the assignment disagree, one of them is lying.
* A determinism test: same input plus fixed `random_seed` yields the same solution.
* Anything asserting the canonical position numbering must use `max_solutions=1` or check the
  whole shortlist: `_ranking_key` imposes an order of its own and will otherwise mask a missing
  symmetry-breaking constraint.
* UI tests (`tests/test_app.py`) drive `streamlit.testing.v1.AppTest` in-process;
  `tests/conftest.py` puts `app/` on `sys.path`, reproducing what `streamlit run app/Home.py`
  does. Address widgets by key, not index. `test_the_ui_inlines_no_german_literal` scans `app/`
  for umlauts outside docstrings; `test_no_string_key_is_missing_from_i18n` globs `app/` too, so a
  UI-only key is not reported unused (dynamically looked-up keys need a prefix in
  `dynamic_prefixes`).
* Coverage gate: ≥ 90 % on `src/dancepartner/` (currently 100 %), with `i18n.py` omitted. The UI
  has its own tests but no gate.

---

## 13. Non-goals and constraints

* No authentication, multi-tenancy, or database.
* No heuristic or genetic solver. The instance is tiny; CP-SAT solves it exactly, and any fallback
  is dead code that drifts out of sync with the constraint set.
* No inferred preferences — no transitive wishes, no "A likes B so B probably likes A", no
  clustering.
* No modelling of height, appearance, choreography paths, or anything the coach did not ask for.
* No real survey data in the repo. `data/team.yaml` is gitignored; only the example files are
  tracked.
* Ask before changing anything in §3 or §6 — the glossary and the hard constraints are the parts
  the team has actually agreed on. (The English-vocabulary rename in §2.1 was agreed this way.)
