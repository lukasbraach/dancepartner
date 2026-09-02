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
* **All user-facing strings in the Streamlit UI and the CLI: bilingual, English (default) and
  German.** They route through `dancepartner/i18n.py`, one flat `dict[str, str]` per language
  with a shared English key set and, per key, identical format placeholders (the test suite
  enforces both). The language comes from `DANCEPARTNER_LANG` (`en`/`de`, unset or unknown →
  `en`), read once at import — Typer help texts resolve then — and the UI switches it per rerun
  from a sidebar toggle held in session state. The active language is a process-wide setting;
  two concurrent browser sessions in different languages can interleave core-rendered strings
  for one rerun, which is acceptable for a single-coach tool. Never inline a user-facing string
  literal, in either language, in a widget call or a `print`.
* Where an English identifier replaced a German term the team actually says, its docstring names
  the old term once (`is_pole_position` — formerly *Startanspruch*). That is a breadcrumb for
  readers who know the team's vocabulary, not a licence to reintroduce the German spelling as an
  identifier.

### 2.1 History

Until the end of Milestone 3 this section mandated the German nouns verbatim as identifiers
(`has_startanspruch`, `Role.HERR`). That produced a codebase in two languages, with the seam
running through the data model, the storage format and the test suite, so the team agreed to move
to the English `leader`/`follower` vocabulary the wider dance world uses. User-facing output was
German-only (accessor `de()`, single table) until English support arrived with the bilingual
tables and the `t()` accessor described above. There is **no backwards
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
| `needs_coaching` | Coachingbedarf | Dancer must **not** be the only one of their role on a position, and the same-role dancer alongside them must not need coaching themselves — every coaching dancer is paired with an experienced dancer of their role. Hard constraints. |
| `desired_tiers` | Wunschpartner | Ranked list of sets of desired partners. Tier 1 = strongest wish. Sets within a tier are equivalent. |
| `not_desired_tiers` | Nicht-Wunschpartner | Same structure, for undesired partners. |
| `coach_constraints` | Trainervorgabe | Hard rules the coach sets themselves, independent of the Teambefragung: `together` = these dancers share one position, `apart` = no two of them do. They name **dancers, never a position label** — positions stay interchangeable. |
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
│   ├── i18n.py          # bilingual UI strings (EN default, DE)
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

The page modules are English with localized sidebar titles supplied via `st.navigation` /
`st.Page(title=t(...))`: Streamlit derives a file-based page's label from its filename, which
would put untranslated identifiers outside `i18n.py`, and a numeric prefix like `1_Team` is not a
valid module name under `mypy --strict`. Ordering comes from the page list.

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
    needs_coaching: bool = False      # must share their role's slot with an experienced dancer

class Tier(BaseModel):
    rank: int                    # 1 = strongest preference
    dancer_ids: frozenset[str]   # equivalent options within the tier

class Survey(BaseModel):
    dancer_id: str
    desired_tiers: list[Tier] = []
    not_desired_tiers: list[Tier] = []

class CoachConstraints(BaseModel):
    together: list[frozenset[str]] = []   # must share one position
    apart: list[frozenset[str]] = []      # no two of them may share a position

class Team(BaseModel):
    dancers: list[Dancer]
    surveys: list[Survey] = []
    n_positions: int = 8
    coach_constraints: CoachConstraints = CoachConstraints()
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
8. Every coach-constraint group names at least two dancers — a group of one constrains nothing,
   and keeping it would let the coach believe they had set a rule.
9. No coach-constraint group is repeated within its kind.
10. Every id named by a coach constraint exists in `dancers`.

The same pair appearing in both `together` and `apart` is *not* a validator: it is a countable
contradiction, and §7 reports it in the coach's language rather than pydantic raising English at
them.

**Preferences are directed.** A wishing for B does not imply B wishing for A. Both directions are
scored independently and are never silently symmetrised. (Hard *vetoes*, §8, are the one symmetric
exception — a pair either shares a position or does not, by construction.)

Preferences read most naturally as *cross-role* (a leader names followers), but same-role entries
matter too: on a Doppelbesetzung two leaders share a position and their working relationship
counts. `PreferenceScope` selects `ALL` (**default**) or `CROSS_ROLE_ONLY`; same-role preferences
are scored only when both dancers share a position. `ALL` is the default because the team answers
the survey expecting every name they wrote down to count — silently dropping the same-role half
reads as a bug to them, not as a modelling choice.

---

## 7. Feasibility pre-check (`feasibility.py`)

Runs before the CP-SAT model is built and returns structured, coach-readable diagnostics
(localized through `i18n.py`), so the solver never returns a bare INFEASIBLE for a cause that is
decidable by counting.

With `n = len(leaders)` and 8 positions:

* Exactly `n - 8` positions carry two leaders, exactly `16 - n` carry a single leader.
* Therefore: `count(is_pole_position ∧ LEADER) ≤ 16 - n`
* And: `count(needs_coaching ∧ LEADER) ≤ n - 8` — two coaching dancers never share a
  position (§8), so each needs their own doubled position.
* And: `8 ≤ n ≤ 16`

Identical checks for followers, plus a check for hard vetoes (§8) making a role infeasible. Each
failure is a `FeasibilityIssue(code, message_de, involved_ids)` the UI can surface.

The coach's own rules (§8, 7.) get the same treatment, all seven of them pure counting arguments,
run on the **transitive closure** of the `together` groups (`feasibility.together_components`) so a
chain `{a,b} + {b,c}` is checked as the `{a,b,c}` it really is:

* `COACH_TOGETHER_TOO_MANY_OF_ROLE` — a component holds more than two dancers of one role.
* `COACH_TOGETHER_NEEDS_DOUBLES` — components each needing their own doubled position for a role
  outnumber the doubled positions that role has. Components are disjoint, so this is exact.
* `COACH_TOGETHER_POLE_POSITION` — a component would make an `is_pole_position` dancer share.
* `COACH_TOGETHER_TWO_COACHING` — a component pairs two `needs_coaching` dancers of one role.
* `COACH_TOGETHER_VETO` — a component contains a pair a hard veto keeps apart.
* `COACH_TOGETHER_AND_APART` — an `apart` group has two members inside one component.
* `COACH_APART_TOO_MANY` — an `apart` group has more members than there are positions.

They run after the role-count and veto checks: the doubled-position arithmetic they rest on is
meaningless until the role counts are in range.

These checks are **necessary, not sufficient** — they find real obstacles but prove no
solvability. `tests/test_cli.py::COUNTING_CLEAN_BUT_INFEASIBLE` is the executable form of that
claim: an instance that passes every counting check and is still INFEASIBLE. Do not "fix" the
pre-check to catch it; that needs general matching, which is the solver's job.

---

## 8. Solver (`solver.py`)

### Two backends

`solver.py` is a dispatcher; the model lives in a backend beside it. Everything below describes
one model, stated twice.

| Module | Solver | Where it runs |
|---|---|---|
| `cpsat.py` | OR-Tools CP-SAT | local, server |
| `highs.py` | HiGHS, as a MILP | local, server, **and the browser** |
| `results.py` | neither — the shared result types and stage vocabulary | everywhere |

CP-SAT is the reference implementation and the default. HiGHS exists because ortools has no
WebAssembly wheel and highspy does, so it is the only one of the two the browser build can
install (§14.2). Choice is the `backend` argument, then `DANCEPARTNER_BACKEND`, then the first
importable one; `SolveResult.backend` records which ran, and `solve --json` carries it.

The two must agree, and the way that is enforced is by running the **existing** suite against
both (`pytest --backend=highs`, and the `highs-backend` CI job) rather than by writing a second
set of tests. `tests/helpers.py::assert_result_valid` re-derives every hard constraint and every
stage value independently of whichever solver produced them, which is what makes that worth
anything. Two tests are marked `cpsat_only`: both measure CP-SAT's own search effort, which is
not a claim about the model.

Where they are compared directly, the assertion is on the **stage value vector**, never on the
assignment — several assignments are genuinely equally optimal and the two break ties
differently.

`solver.py` itself imports neither backend, which is what lets the browser ship it for
`SolveResult` and the type annotations while installing only HiGHS.

### What the MILP has to spell out

CP-SAT states implications directly; a MILP linearizes them. The translations are in
`highs.py`, and three are worth naming because they are where a mistake would be silent:

* `together` becomes the standard AND — `b ≤ x_d`, `b ≤ x_e`, **`b ≥ x_d + x_e − 1`**. The third
  row is the counterpart of the reverse implication below, and just as mandatory.
* `doubled` needs no reification at all: the role count is already confined to `{1,2}`, so
  `Σ x == 1 + doubled` defines the flag and the bound together. Pole position and coaching need
  then reduce to `doubled + x ≤ 1` and `doubled ≥ x`, with no big-M anywhere.
* `max` (the `BEST` aggregation) needs a selector: `best ≥ c_i v_i` for every operand, plus
  `best ≤ c_i v_i + M(1 − y_i)` with `Σ y_i = 1`. Only the upper half stops the solver inflating
  `best`; only the lower half stops it understating one. The pins and the enumeration replay
  both need it exact in *both* directions.

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
5. Per position and per role, at most one dancer with `needs_coaching` — combined with 4.,
   every coaching dancer is paired with an experienced same-role dancer.
6. Optional hard veto: if `SolverConfig.veto_tier` is set (default `1`), all `not_desired` entries
   at that tier or stronger get `together[d, e] == 0`.
7. The coach's own rules, `Team.coach_constraints`. Stated on `x` directly rather than on
   `together[d, e]`, which only exists for pairs somebody wrote a wish about:
   `together` → `x[anchor, p] == x[other, p]` for every `p`, over the connected components of the
   groups; `apart` → `add_at_most_one(x[d, p] for d in group)` for every `p`. No new variables, no
   big-M and no objective stage, so the enumeration pass's stage replay is untouched.

A coach constraint names **dancers, never a position label**, which is what makes it compatible
with the symmetry breaking below: pinning somebody to "position C" would contradict the canonical
numbering the whole search rests on, while "together" and "apart" say all there is to say without
naming a label. Unlike a veto, `apart` is the coach's decision rather than a survey answer, so
`veto_tier` does not reach it.

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

Integer arithmetic only. How one dancer's fulfilled wishes combine is
`SolverConfig.aggregation`:

* `BEST` — **default.** `score[d] = max_e{ weight(d, e) * scale * together[d, e] over desired
  entries, 0 if none } + Σ negative weights of violated dislikes`. Satisfaction saturates: a
  dancer with their tier-1 partner and no violated dislike scores the instance-global top-tier
  weight, and a second fulfilled wish adds nothing. This matches how the team reads the result
  — one strong partnership per dancer is the goal — and it makes scores comparable across
  dancers, which is what leximin levels.
* `SUM` — `score[d] = Σ_e weight(d, e) * together[d, e]`, the original semantics, kept
  selectable.

The tier-count stages of `LEXICOGRAPHIC_TIERS` count `together` variables and are
aggregation-independent.

Tier weights (`scoring.tier_weight`) are fixed, not selectable: tier *k* of *K* is worth
`K - k + 1`, dislikes negative and symmetric. `K` is instance-global, so a dancer who listed
one tier is not scored lower than one who listed three.

There is deliberately **no geometric scheme**. One was tried (`B^(K-k)` with `B` derived from
the instance, so that a single tier-*k* fulfilment outranked every possible tier-*(k+1)* one)
and removed: on a 22-dancer instance with four tiers `B` came out at 67, which made a granted
second choice read as 1 % satisfaction against 100 % for a first — a faithful rendering of the
weights and a useless one for the coach. It also blew up the objective's coefficient range,
degrading CP-SAT's bound quality on larger instances. Strict tier ordering is
`Objective.LEXICOGRAPHIC_TIERS`'s job, staged rather than smuggled into the coefficients.

**Normalisation** (`SolverConfig.normalize_double`, default on). A dancer with two cross-role
partners has twice the score contributions; unnormalised, the solver systematically favours
Doppelbesetzungen for well-liked dancers. What doubles a dancer's cross-role contributions is the
number of dancers of the **other** role on their position, not their own role's count — see
`solver._partner_doubled`. Scores live on a ×2-scaled integer scale
(`SolverConfig.score_scale`) so the doubled case halves without rounding. The halving uses two
linear equalities under `only_enforce_if` rather than `add_multiplication_equality`: the factor is
binary, so they are exactly equivalent, stay linear, and propagate far better.

Under `BEST` the halving applies to the **negative side only**: it corrects double-*collection*
of summed contributions, and a maximum cannot double-collect. Halving the max would make a
doubled dancer with a fulfilled tier-1 wish look half as happy as a single one for no semantic
reason, and it would break the fixed 100 %-denominator below. The positive part is encoded with
`add_max_equality` over the affine terms `weight * scale * together` — each is 0 or the scaled
weight, so an empty fulfilment maxes to 0 without an explicit operand.

**Satisfaction ratio** (`reporting.satisfaction_ratio`, BEST only). Per dancer,
`score / (top-tier weight × scale)` — so "tier-1 wish fulfilled, nothing violated" is exactly
100 % for everyone, single or doubled. A dancer whose survey holds only dislikes starts at
100 % and loses per violation. A dancer with no in-scope entries at all is `None`: neutral,
not unhappy, and rendered without a colour.

Normalisation also interacts with `prefer_coupled`: a granted wish is worth more when the position
holds a single dancer of the opposite role, so `abs(n_leaders - n_followers)` is only a lower
bound on the lopsided count, not an attainable target. Wishes first is the intended trade.

### Objective staging

`SolverConfig.objective` selects one of:

* `WEIGHTED_SUM` — single-stage `maximize(Σ score)`. Simplest, and reliably leaves one or two
  people with nothing. Kept for comparison.
* `MAXIMIN_THEN_SUM` — Stage 1 maximises `lo` with `lo ≤ score[d]` for all `d`.
  Stage 2 pins `lo` to its optimum and maximises `Σ score`. Lifts the worst-off dancer once and
  then stops caring about them.
* `LEXIMIN` — **default.** Two stages per round: maximise the floor among the dancers still in play, then
  maximise how many escape it. The "in play" indicators are reified from the scores, so the solver
  picks *which* dancers escape while the stage fixes only *how many* — that is what makes it a
  leximin instead of a maximin repeated on an arbitrary set. The rounds pin the entire sorted
  score vector, so `LEXIMIN` needs no `sum` stage and every optimum has the same total. It is the
  default because it keeps going down the list where `MAXIMIN_THEN_SUM` stops at the floor.
  One consequence: `near_optimal_ratio` computes its band per stage from that stage's optimum, and
  leximin's stage optima are single-dancer scores, so a few percent of them rounds to zero. The
  knob effectively only widens the shortlist under `MAXIMIN_THEN_SUM`, whose `sum` stage is large
  enough for a percentage to bite.
* `LEXICOGRAPHIC_TIERS` — counts fulfilled wishes per tier rather than scoring them, so the
  tier weights never enter the objective. The mirror-image dislike stages (`not_desired.tierN`,
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
  can coincide, and the example team's two optima are exactly that case.
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

`reporting.exchange_groups` / `group_numbers` derive the **exchange groups** both surfaces
mark: whom the coach can swap through without making the team unhappier. A group is a set of
dancers in **one** solution such that *every* permutation of them over their positions keeps
every hard constraint and the solution's sorted per-dancer score vector — three dancers form
a group of three only when all six arrangements hold. Interchangeability is not transitive,
so groups are grown greedily in (label, id) order and verified against full permutation
closure on every extension (capped at `MAX_GROUP_SIZE`); permuted assignments are re-validated
and re-scored directly via `build_satisfaction`, so the result never depends on which other
solutions the enumeration pass returned before its cap. Groups are role-pure by physics, not
by fiat — a cross-role permutation would change a position's role counts. Co-positioned
dancers are never grouped (their "swap" changes nothing), and one-sided relocations that
resize positions (a follower moving from a doubled position onto a single one) are not
permutations: those alternatives stay visible in the solution browser. Numbering is
deterministic: group 1 holds the alphabetically first position.

---

## 9. Persistence (`storage.py`)

YAML in `data/`, human-editable and diffable. `load_team(path) -> Team`, `save_team(team, path)`,
`dump_team(team) -> str`. Since §10's save became a download, `save_team` is used only by the
storage tests; it stays as the documented counterpart to `load_team` and as what `dump_team`
is specified against.
No database.

* Canonical output: `sort_keys=False` with a fixed key order — PyYAML left to itself shuffles
  `id`/`name`/`role` on every save. Dancer order is preserved — it decides which letter a group
  of leaders lands on via `solver._break_symmetry`, so a reordered file yields a relabelled but
  equally good solution (§8, §10).
* Tiers are stored as `rank: [ids]` mappings under `desired:` / `not_desired:`, emitted inline
  (`1: [anna-b, lena-f]`). False flags and empty survey directions are omitted.
* Key order at the top level: `n_positions`, `dancers`, `surveys`, `coach_constraints`. The last
  two are omitted entirely when empty. Coach constraints are stored as
  `coach_constraints: {together: [[ids]], apart: [[ids]]}`, each group emitted inline like a tier.
  The model holds them as sets, so both the ids inside a group and the groups themselves are
  sorted on the way out — otherwise the file churns between saves.
* PyYAML cannot preserve comments, so serialising drops them. `load_team` never writes; writing
  happens only on explicit request (CLI `--json` flag; the UI writes nothing at all and hands the
  coach a download instead — never autosave).
* `StorageError` means the YAML *shape* is wrong; `ValidationError` means a §6 domain rule broke.
  The CLI maps both to localized messages and exit code 1.
* Real survey data never enters the repo: `data/team.yaml` is gitignored, only the two example
  files are tracked.

---

## 10. Streamlit UI (`app/`)

A home page and four working pages, all thin over `app/common.py` (session state, the cached
solve, formatting):

* `Home.py` — upload or create a team, or load the bundled example; feasibility summary panel
  (§7); explicit save as a **download**. Neither side prints a path: the app has no writable path
  of its own once it is served to a browser, and `st.download_button` is the honest counterpart to
  the uploader. Pressing it is what clears the unsaved-changes warning (`common.mark_saved`).
* `pages/team.py` — dancer table with `st.data_editor`: name, role, pole position, coaching need.
* `pages/survey.py` — pick a dancer, then per direction a dynamic list of tiers, each an
  `st.multiselect` over eligible dancers, with add/remove tier buttons.
* `pages/solution.py` — solver config widgets, a run button, the best solution as 8 cards with
  badges for fulfilled wishes and violated dislikes. Dancers in an exchange group carry their
  group's number emoji (1️⃣–🔟, plain text past ten) next to their name, with a caption
  pointing to the analysis page.
* `pages/analysis.py` — per-dancer satisfaction sorted ascending (the unhappiest first — that is
  the row the coach actually needs) with an exchange-group column, an **exchange groups**
  block naming each freely interchangeable set with its positions (computed for the selected
  solution), plus a browser over the enumerated solutions with a diff against the selected
  one.

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
* Editing pages validate §6 rules 3 and 4 **themselves** so the conflict reads in the coach's
  language, through `i18n.py`. Pydantic stays the final gate, but its raw message must never
  reach the coach.
* The team page carries the coach-constraint editor below the roster: the rules name dancers from
  the table above, and deleting a dancer prunes them in the same apply step. A rule is dropped
  **whole**, never shrunk — "keep these three together" minus one dancer is a different rule, and
  the coach never asked for it. Rules with fewer than two dancers and duplicates are refused in
  the page, in the coach's language, per the rule above.
* `st.rerun` throws the current run away, so a notice written just before it is never drawn. The
  team page parks its notices in session state and renders them at the top of the next run.
* Empty and orphaned tiers are renumbered, not rejected — browser editing breaks the "contiguous
  from 1" rule constantly, and the coach did not cause it. See `common.renumber_tiers` /
  `tiers_from_selections`.
* Colour encodes satisfaction only, never name or role. Under `ScoreAggregation.BEST` the scale
  is **absolute**: `common.ratio_badge` over `reporting.satisfaction_ratio`, the analysis table
  shows a 0–100 % progress column, and a dancer with no stated preference renders grey (⬜),
  never red. Under `SUM`, `common.score_badge` keeps scaling against the achieved range of the
  solution being shown. Exchange groups are marked with **number** emoji (`common.group_marker`)
  precisely so they never compete with the colour channel.
* `st.data_editor` is fed `list[dict]`, not a DataFrame (§4 keeps pandas out).
* The solve page's main area holds only what changes the answer the coach is looking at —
  objective, aggregation, scope, veto rank, and the two normalisation switches. Search budget
  (`max_solutions`, `max_time_in_seconds`) and the two fine-tuning knobs (`near_optimal_ratio`,
  `tier_slack`) live behind **More settings**: they change how long the search runs or how wide
  the shortlist is, never what "good" means.
* The team page carries **no** note about roster order. Order only decides which letter a group
  of leaders lands on (`solver._break_symmetry` fills positions in leader-list order); it cannot
  change solution quality, `Solution.signature` ignores labels entirely, and the page offers no
  way to reorder — so the note raised a question it could not answer.
* Ranks are never shown as "Tier N". `tier.desired` / `tier.not_desired` name them per direction
  ("Wish 2" / "No-go 1", "2. Wunsch" / "1. Nicht-Wunsch") and `table.*` / `explain.entry` compose
  that label in, so the wording lives in one place per language. German is the reason the label is
  direction-specific: "1. Wunsch" over a list of *un*wanted partners says the opposite of what it
  means.

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
  `ObjectiveChoice`/`AggregationChoice`/`ScopeChoice` enums, mapped to the domain
  enums by member name. The domain enums keep snake_case values because YAML and JSON carry
  those. `--aggregation best|sum` selects the score aggregation (§8); under `best`, `explain
  --dancer` adds a satisfaction percentage line for dancers with in-scope preferences.
  A result file written before the field existed reads back as `best` (the pydantic default) —
  accepted, consistent with §2.1's no-backward-compatibility stance; the stored scores
  themselves are never recomputed by `explain`.
* `--veto-tier 0` is the CLI spelling of `SolverConfig.veto_tier=None`.
* `--top N` sets `max_solutions` **and** prints all N, each alternative diffed against the best.
  When the best solution has exchange groups (§8 `reporting.exchange_groups`), the shortlist
  header is followed by one line per group — its dancers with their positions. `--near-optimal`
  and `--tier-slack` expose the other two enumeration knobs.
* `solve --json` writes `{"config": ..., "result": ...}`; `explain` reads that back. Keep both
  ends in step — `test_explain_matches_the_solve_table` compares their rendered output.
* `explain --solution N` picks a shortlist entry and names the dancer's exchange group when
  they belong to one in that solution; with more than one solution in the file it also
  summarises how stable the dancer's partners are across the whole shortlist. That is the
  question enumeration exists to answer: a partner in every optimum is not a choice the coach
  has to make, one in 3 of 20 is.
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
* `assert_valid` re-derives the hard constraints from the `Solution` and the `Team` alone,
  numbered to match §8 — including the coach's rules, whose `together` closure is recomputed there
  rather than read off the groups as written, so a chained rule cannot pass by being checked
  pairwise.
* The load-bearing constraints are verified by mutation — each of these must turn the suite red:
  the `add_bool_or` half of the reification, the at-most-one-coaching-dancer constraint, the
  symmetry-breaking constraint, the signature dedup, the `_lock_in` tie-break guard.
* `tests/test_objectives.py::divergent_instance` is the instance where maximising the total and
  levelling up genuinely disagree (`MAXIMIN_THEN_SUM` reaches `[0, 0, 2, 6, 6, 6, 6]`, `LEXIMIN`
  gives up five points of total for `[0, 2, 2, 3, 4, 4, 6]`). Without it the two objectives look
  identical on every instance in the repo. The divergence test pins
  `ScoreAggregation.SUM` — the hand-derived vectors are summed arithmetic; the SUM-vs-BEST
  disagreement has its own instance in `test_sum_and_best_optima_genuinely_differ`.
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
* With two backends, **no single run can reach 100 %** — whichever solver is idle looks dead. The
  90 % gate stays on the single-backend run; `make cov-both` (and the `highs-backend` CI job) runs
  the suite twice and combines, which is where the real figure comes from. `pytest --backend=X`
  selects; `@pytest.mark.cpsat_only` excuses the two tests that measure CP-SAT's own search effort
  rather than the model.

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

---

## 14. Deployment

Three ways to run the same `app/`: `make ui` on a laptop, a Docker image behind Caddy on a private
server, and a static [stlite](https://stlite.net) bundle on GitHub Pages. §1–§13 describe the tool;
this section describes where it runs and what changes when it does.

### 14.1 Two targets, one codebase

Neither target adds a runtime dependency, restructures `app/`, or introduces a backend. In
particular there is no `DataSource` abstraction over "local file vs S3 vs database": there is no
database (§9), no multi-tenancy (§13), and the core/UI split already lives in `src/` vs `app/`. The
only real difference between the targets is whether the solver exists, and that is one boolean.

### 14.2 Which solver the browser gets

`ortools` has no WebAssembly wheel. Every wheel published to PyPI is macOS, Linux or Windows
specific — there is no `py3-none-any` fallback — and Pyodide's distribution does not carry it.
`highspy` **does** ship `highspy-1.11.0-cp313-cp313-pyodide_2025_0_wasm32.whl`, so the browser
solves with the HiGHS backend (§8) while local and server installs default to CP-SAT.

That constraint is still what shapes the module layout. `cpsat.py` is excluded from the bundle,
and `solver.py` — the dispatcher — imports neither backend, so it can ship. `dancepartner/__init__.py`
resolves only `solve` through a PEP 562 `__getattr__`: importing any submodule runs the package
`__init__` first, so an eager import of a *backend* would mean `from dancepartner.model import Team`
pulls in CP-SAT, and the browser could not import the data model at all. §5's import-direction rule
gains one clause: **a backend is reachable from `__init__` only lazily, and `app/` never imports one
at module level.** `tests/test_wasm_deps.py` and the `wasm-parity` CI job enforce both halves.

Being able to solve everywhere is worth more here than solving fastest, which is the trade the
`highs.py` formulation makes. HiGHS has no solution pool, so enumeration re-solves with a no-good
cut per assignment instead of walking one search — see §8's enumeration notes.

### 14.3 Degrading explicitly

`app/common.py` exposes `SOLVER_AVAILABLE`, asked of the dispatcher (`available_backends()`)
rather than of one package or of the platform. It is normally true everywhere, the browser
included; it goes false only where neither backend is installed — a CLI-only install of the core,
say. There, Solution and Analysis render `ui.solver.unavailable` and stop, and Home says so up
front. Neither page leaves `st.navigation`: a missing menu entry is a worse lie than a page that
explains itself. Analysis checks the capability *before* `require_result()`, or the coach would be
told "no solution computed yet", which misstates the cause.

### 14.4 Drafts

§9 said the UI writes nothing at all. That is amended to: **the UI never writes the coach's file; a
draft it may.** `st.download_button` is still the only export, and a draft never clears the
unsaved-changes warning — it is not a save and is never presented as one.

The rule existed because PyYAML drops comments, so an autosave would quietly strip the documentation
out of a hand-written team file. A draft touches no file of the coach's, so that reasoning does not
reach it — and losing an evening of survey entry to an accidental reload is a real cost the rule was
never meant to impose.

`app/persistence.py` keeps one, with a backend per target because a reload means different things:

* **Browser** — one YAML file per version on an stlite `idbfsMountpoints` directory, which is
  IndexedDB. A reload restarts the whole Pyodide worker, so nothing in Python memory could survive;
  the mount does. stlite flushes it after every script run, so Python just writes the file. The
  mountpoint must be a single top-level directory: stlite mounts with a bare `FS.mkdir`, and a
  nested path fails the entire boot with an `ErrnoError` before Streamlit renders.
  `build_static.IDBFS_MOUNTPOINT` and `persistence.MOUNTPOINT` are held together by a test.
* **Server** — a `secrets.token_urlsafe(16)` in `?draft=`, the one piece of state a refresh keeps by
  itself, keying an in-RAM `st.cache_resource` store with a 12 h TTL and LRU eviction. Process
  memory only: unlike `st.cache_data` there is no `persist=` to turn on by accident.

Both are best effort and swallow their own failures. A private window with IndexedDB disabled
degrades to "a reload loses the team", which is where this project started.

#### Versions

Each **load** — an upload, the example, a fresh team — mints a new token and leaves the previous
draft in place; each **edit** overwrites the current one. So loading something else does not destroy
what was open, and a survey keystroke does not add a history entry. `MAX_HISTORY` (10) versions are
kept per browser; the browser build prunes the mount, which nothing else garbage-collects.

The history is offered as a list on Home, not through the browser's back button, and that is not a
UX preference. **streamlit#13963**: in a `st.navigation` app a back press changes the URL and reruns
the script, but `st.query_params` still reports the *newest* value, so the app cannot tell which
version the URL points at. `st.context.url` is no way out — it carries no query string at all. Both
verified in a browser against 1.62; the browser build's bundled 1.57 is older still. If that bug is
ever fixed, back-navigation becomes a second trigger for the same stored history.

The two targets differ in what survives a reload, and the difference is worth stating plainly: the
browser build reads its history off the mount, so all of it comes back; the server build keeps the
history in session state, so a reload restores the current version through the URL but not the
older ones.

### 14.5 Where the data actually is

Stated per target, because the honest answer differs:

* **Local** — nothing leaves the machine.
* **Browser** — nothing leaves the device. The only network traffic is the stlite and Pyodide
  fetch from jsDelivr, which carries no team data. The IndexedDB draft stays in that browser
  profile until it is discarded or the profile is cleared.
* **Server** — survey answers live in that server's memory for the session, and for up to the 12 h
  draft TTL. Nothing reaches its disk: the container runs `read_only`, with tmpfs for `/tmp` alone.
  The draft token appears in the URL bar, in browser history, and would appear in Caddy's access
  log if the Caddyfile did not strip it. Anyone with that URL, inside the authenticated perimeter,
  can read that draft. It is not the security boundary — Caddy's authentication is, and TLS and
  authentication are Caddy's job in full. The app has none and must keep having none (§13).

### 14.6 The config comment

`.streamlit/config.toml` used to say "Nothing about it should leave the machine it runs on." That is
true of the local and browser targets and false of the server one. The telemetry claim it was
attached to — that nothing is reported to Streamlit's usage statistics — holds everywhere; the
data-location claim is 14.5's business, and the comment now points there instead of asserting it.

### 14.7 The first visit, and every one after it

Three things the browser target needs that a served app gets for free.

**A boot screen that means something.** A cold load pulls roughly 30 MB and takes several seconds
even on a fast connection. stlite narrates that with "Loading Pyodide", "Unpacking archives",
"Mocking" — accurate, and not addressed to a dance coach. `wasm/index.html.j2` therefore paints its
own overlay, **outside `#root`** and fixed on top, and steps through `ui.loading.*` on a timer:
getting ready, downloading, preparing the solver, nearly there. Both language tables are baked into
the shell at build time (it renders before Python exists) and it picks one from `?lang=`, falling
back to `navigator.language`.

It comes down when the app is genuinely up, which means **content inside `[data-testid="stMain"]`**
— not the container, which stlite renders empty within a few hundred milliseconds of a load that
takes several seconds. A 120 s timeout removes it regardless, so a broken deploy shows a broken app
rather than a spinner forever.

**A service worker.** `wasm/sw.js.j2` caches the runtime, which is what makes the app installable
in any useful sense and what makes it work offline. Two caches: one keyed by the stlite and Pyodide
pins, holding the ~30 MB from jsDelivr, and one keyed by the shell's own content hash. Separate on
purpose — sharing a name would re-download the runtime after a one-line UI fix. `activate` deletes
everything outside that pair.

It claims the page on install rather than waiting for the next navigation. Measured in Chrome: the
one load that actually pulls the 30 MB is otherwise the one load that goes uncached. Pyodide runs in
a Web Worker created from a `blob:` URL and that worker inherits the page's controller, so its
fetches are cached too — verified by reading the cache back after a cold load (68 entries,
`pyodide.asm.wasm`, `python_stdlib.zip` and the `highspy` wheel among them).

**Deep links.** The pages are client-side routes; a static host has no file behind `/survey`. Three
layers answer it with the shell: `404.html` (a byte copy of `index.html`) on Pages, the service
worker on any return visit, and `wasm/serve.py` locally — which is why `make wasm-serve` no longer
uses `python -m http.server`.

That alone lands the coach on the *start* page with `/survey` still in the address bar, because
stlite's client does not resolve the path the way Streamlit's own server does. Python cannot resolve
it either: under stlite `st.context.url` is the bare origin, no path and no query string. So the
shell copies the path into `?page=`, which the script *can* read, and `common.initial_page` switches
to it once and clears the parameter. The shell rewrites the address back to the base path when it
does — `st.switch_page` resolves relative to wherever the address bar points, so leaving `/survey`
there produces `/survey/survey`.

**Feedback while it solves.** Writing an element is not what puts it on screen. Streamlit hands it
over immediately, but under stlite the delivery needs the Pyodide worker's event loop, and a script
run that goes straight from drawing a busy banner into a solve never gives it a turn — so the
banner arrives together with the answer, which is to say never. Splitting the click across extra
reruns does not help either; ending a run is not a yield.

What yields is sleeping. `common.flush_ui()` sleeps 50 ms between the banner and the solver, and
`solve_and_store` calls it so a page cannot forget to. Measured in Chrome against a 1.3 s solve: the
banner appears 0.10 s after the click and stays until the answer replaces it. 50 ms is enough; the
same run without it shows nothing at all, which is how this was found.

### 14.8 The language preference

The sidebar toggle is per session, and a session ends at every reload. Two mechanisms put it back:

* `?lang=` in the URL, stamped by `app/persistence.py` next to the draft token. It survives a reload
  on **both** targets, it is what a shared link carries, and it is the only way the static shell can
  know which language to write its boot screen in.
* A one-line file on the IDBFS mount, browser build only. That covers a genuinely fresh visit and a
  PWA launched from the home screen, neither of which carries a query string.

Not `localStorage`, which is the obvious answer and not available: Python runs in a Web Worker here,
and Web Workers have no `localStorage` at all — it is synchronous and main-thread-only. IndexedDB is
what a worker does get, and the draft mount is already IndexedDB and already flushed after every
script run, so the preference rides along with it.

The server build has no store, deliberately: process memory would leak one coach's choice into the
next coach's session, and the container filesystem is read-only (14.5). It persists through the URL
and nothing else.

Resolution order, in `common.sync_language()`: session state, then `?lang=`, then the stored file,
then `DANCEPARTNER_LANG`. The URL beats the store because it is the more deliberate act. Anything
unrecognised is ignored rather than raised — a hand-edited URL must not be able to break the page.

### 14.9 Pinned versions

    @stlite/browser 1.8.1  ->  Pyodide 0.29.3  ->  CPython 3.13.2  ->  streamlit 1.57.0

Pinned in `wasm/build_static.py`, never a floating CDN tag: a stlite bump moves Pyodide, and Pyodide
is what decides which `pydantic` exists. Note the last link — the browser runs streamlit 1.57, not
the 1.62 in `requirements-dev.txt`.

Moving the pin means: bump `STLITE_VERSION`, re-derive the Pyodide version, regenerate
`wasm/pyodide-lock.trimmed.json` (the command is in the header of `wasm/requirements-wasm.txt`), and
re-pin `requirements-wasm.txt` to whatever that Pyodide carries. `build_static.py --check-lock`
catches a stale index in CI; `wasm-parity` catches a pydantic that behaves differently.

A new runtime dependency clears three gates, not one:

1. `pyproject.toml`, then re-freeze `requirements-dev.txt`.
2. If `src/dancepartner/` imports it outside `solver.py`/`cli.py`, it must exist in the Pyodide
   index — add it to `requirements-wasm.txt` pinned to *exactly* that version. A pure-Python
   `py3-none-any` wheel from PyPI also works; a compiled extension does not, unless Pyodide builds
   it.
3. If it cannot run in the browser, it gets the `ortools` treatment: confined to one module,
   reached only through a dispatcher that imports it lazily, excluded from the bundle by
   `build_static.SERVER_ONLY`, and gated in the UI behind a capability flag. Never a bare
   module-level import in something the browser pages need.
