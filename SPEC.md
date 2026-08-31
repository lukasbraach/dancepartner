# `dancepartner` — Build Specification for Claude Code

> **How to use this file:** commit it to the repo root as `SPEC.md`, then start Claude Code with
> *"Read SPEC.md and implement Milestone 1. Do not start Milestone 2 until I confirm."*
> Work milestone by milestone; the solver core must be correct and tested before any UI exists.

---

## 1. Context

We assign dancers of a Latin formation team (Lateinformation, VfL Pinneberg) to **8 unordered positions**.
Each position is occupied by at least one leader and at least one follower, optionally two of each
(*Doppelbesetzung* — two couples share a position and alternate across tournaments).

The team runs an internal survey (*Teambefragung*) in which every dancer names desired and
undesired partners in ranked tiers. We turn the assignment into a constraint optimisation
problem and solve it exactly with OR-Tools CP-SAT.

The final human decision stays with the coach — the tool produces a **shortlist of optimal and
near-optimal assignments**, never a single mandated answer.

---

## 2. Language policy

Read this carefully, it is a recurring source of inconsistency.

* **All code identifiers, comments, docstrings, commit messages, tests and log output: English.**
  No exceptions. This includes the domain terms of art — see §3 for the mapping and §2.1 for why
  this rule changed.
* **The on-disk YAML and JSON use the same English vocabulary as the code.** `role: leader`,
  `desired:`, `not_desired:`, `is_pole_position:`. There is one vocabulary, not two.
* **All user-facing strings in the Streamlit UI and the CLI: German.** Route them through a single
  module `dancepartner/i18n.py` holding a flat `dict[str, str]`; never inline German string
  literals in widget calls. The *keys* of that dict are English, the *values* are German.
* Where an English identifier replaces a German term the team actually says, its docstring names
  the old term once, so a reader who knows the team's vocabulary can still find their way. Do not
  reintroduce the German spelling as an identifier.

### 2.1 History — this rule used to say the opposite

Until the end of Milestone 3 this section mandated the German nouns verbatim as identifiers
(`has_startanspruch`, `wunsch_tiers`, `Role.HERR`) on the grounds that they have no precise
English equivalent. That produced a codebase in two languages, and the seam ran straight through
the data model, the storage format and the test suite.

The team moved to English `leader`/`follower` vocabulary, which is also what the wider dance world
uses, so the exception no longer paid for itself. The renames were:

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

There is **no backwards compatibility**: a team file written in the old vocabulary fails to load
with a `StorageError` naming the offending key. Only the example file was ever tracked, so this is
a one-off manual edit for any private `data/team.yaml`.

---

## 3. Glossary (identifier → meaning)

The German column records what the team used to call each thing. It is there so the vocabulary
shift stays traceable — it is **not** a licence to use those spellings as identifiers.

| Identifier | Formerly (Deutsch) | Meaning |
|---|---|---|
| `Role.LEADER`, `Role.FOLLOWER` | Herr / Dame | The two dance roles. Fixed per dancer, not a preference. |
| position index `p`, label A–H | Position | One of the 8 slots on the floor. Unordered and interchangeable in the model. |
| `is_doubled` | Doppelbesetzung | A position holding two leaders *and* two followers. |
| `is_pole_position` | Startanspruch | Dancer is the sole driver of their position and must **not** share it with another dancer of the same role. Hard constraint. A claim on the starting slot, **not** a ranking. |
| `needs_coaching` | Coachingbedarf | Dancer must **not** be the only one of their role on a position; they need a same-role dancer alongside them. Hard constraint. |
| `desired_tiers` | Wunschpartner | Ranked list of sets of desired partners. Tier 1 = strongest wish. Sets within a tier are equivalent. |
| `not_desired_tiers` | Nicht-Wunschpartner | Same structure, for undesired partners. |
| `Survey` | Teambefragung | One dancer's complete set of answers. |
| `Solution` | Verpartnerung | A complete mapping of dancers to positions. |

Dancers not named in any tier are **neutral**: assignable, contributing zero to that dancer's score.

---

## 4. Tech stack

* Python **3.12**, dependency management with **uv** (`pyproject.toml`, `uv.lock` committed).
* `ortools` (CP-SAT) — solver.
* `pydantic` v2 — data model and validation.
* `streamlit` — UI (Milestone 4 only).
* `typer` — CLI.
* `pyyaml` — persistence.
* Dev: `pytest`, `pytest-cov`, `ruff` (lint + format), `mypy --strict`, `pre-commit`.
* CI: GitHub Actions running ruff, mypy and pytest on push and PR.

No Jupyter notebooks. No pandas unless a milestone explicitly needs tabular output.

---

## 5. Repository layout

```
dancepartner/
├── pyproject.toml
├── SPEC.md
├── CLAUDE.md
├── data/
│   └── team.example.yaml
├── src/dancepartner/
│   ├── __init__.py
│   ├── model.py         # pydantic domain model
│   ├── feasibility.py   # cheap counting pre-checks
│   ├── solver.py        # CP-SAT model construction + staged optimisation
│   ├── scoring.py       # weight schemes, per-dancer satisfaction reporting
│   ├── storage.py       # YAML load/save
│   ├── i18n.py          # German UI strings
│   └── cli.py
├── app/
│   ├── Home.py
│   └── pages/
│       ├── 1_Team.py
│       ├── 2_Umfrage.py
│       ├── 3_Loesung.py
│       └── 4_Analyse.py
└── tests/
```

`src/dancepartner` must have **zero** imports of `streamlit`. The UI depends on the core; never
the reverse. A reviewer should be able to delete `app/` and still run everything from the CLI.

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
    is_pole_position: bool = False     # must be alone in their role on the position
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

Validators, all of which must raise on violation:

1. `is_pole_position` and `needs_coaching` are mutually exclusive per dancer.
2. Tier ranks are contiguous starting at 1, no duplicates.
3. A dancer id appears in at most one tier per direction (no dancer both tier-1 and tier-3 wish).
4. A dancer id appears in **at most one direction** — being both wished and un-wished is a survey
   entry error, not a subtle preference.
5. No self-references.
6. All referenced ids exist in `dancers`.
7. Every dancer has at most one `Survey`.

**Preferences are directed.** A wishing for B does not imply B wishing for A. Both directions are
scored independently and must never be silently symmetrised.

**Design question to model explicitly:** preferences are about *cross-role* partners by default
(a leader names followers). Support same-role entries too — on a Doppelbesetzung two leaders
share a position and their working relationship matters. Represent this with a `PreferenceScope` config
flag: `CROSS_ROLE_ONLY` (default) or `ALL`. Same-role preferences are scored only when both are on
the same position.

---

## 7. Feasibility pre-check (`feasibility.py`)

Run before building the CP-SAT model and return structured, German-readable diagnostics. Do not
let the solver return a bare INFEASIBLE for causes that are decidable by counting.

With `n = len(leaders)` and 8 positions:

* Exactly `n - 8` positions carry two leaders, exactly `16 - n` carry a single leader.
* Therefore: `count(is_pole_position ∧ LEADER) ≤ 16 - n`
* And: `n - 8 ≥ ceil(count(needs_coaching ∧ LEADER) / 2)`
* And: `8 ≤ n ≤ 16`

Identical checks for followers. Report each failure as a `FeasibilityIssue(code, message_de, involved_ids)`
so the UI can surface it. Include a check for hard vetoes (§8) making a role infeasible.

---

## 8. Solver (`solver.py`)

### Variables

* `x[d, p] ∈ {0,1}` — dancer `d` on position `p`.
* `together[d, e]` — reified, true iff `d` and `e` share a position.

### Hard constraints

1. `AddExactlyOne(x[d, p] for p in positions)` for every dancer.
2. Per position and per role: `1 ≤ Σ x ≤ 2`.
3. Pole position: `Add(role_count == 1).OnlyEnforceIf(x[d, p])`.
4. Coaching need: `Add(role_count >= 2).OnlyEnforceIf(x[d, p])`.
5. Optional hard veto: if `SolverConfig.veto_tier` is set (default `1`), all `not_desired`
   entries at that tier or stronger get `together[d, e] == 0`.

### Reification — get this exactly right

```python
b = model.NewBoolVar("")
model.AddBoolAnd([x[d, p], x[e, p]]).OnlyEnforceIf(b)
model.AddBoolOr([x[d, p].Not(), x[e, p].Not()]).OnlyEnforceIf(b.Not())
```

**Both directions are mandatory.** With only the first implication and negative weights present,
the solver will set `b = 0` for a pair that actually shares a position and thereby erase a dislike
penalty. Add a regression test that specifically catches this.

### Symmetry breaking

Positions are unordered — without symmetry breaking the search space is inflated by 8! = 40320.
Enforce a canonical numbering over leaders, ordered by their index in the input list:

```
x[leader_i, p] <= Σ_{j<i} x[leader_j, p-1]     for p >= 1
```

Add a test asserting that the solver finds the same objective value with and without symmetry
breaking on a small instance, and that the constrained run is faster.

### Scoring (`scoring.py`)

`score[d] = Σ_e weight(d, e) * together[d, e]`, integer arithmetic only.

Weight schemes, selectable via `SolverConfig.weights`:

* `LINEAR` — tier *k* of *K* is worth `K - k + 1`, dislikes negative and symmetric.
* `GEOMETRIC` — `B^(K-k)` with `B` large enough that one tier-*k* fulfilment outranks all possible
  tier-*(k+1)* fulfilments. Compute `B` from the instance, do not hardcode it. Warn in the docstring
  that this degrades CP-SAT's bound quality on larger instances.

**Normalisation.** A dancer on a Doppelbesetzung has two cross-role partners and thus twice the
score contributions; unnormalised, the solver systematically favours Doppelbesetzungen for
well-liked dancers. Implement `SolverConfig.normalize_double: bool = True`: introduce
`is_doubled[d]` (bool) and use `AddMultiplicationEquality` to halve the doubled case, working on a
×2-scaled integer score so no rounding is needed.

### Objective staging

`SolverConfig.objective` selects one of:

* `WEIGHTED_SUM` — single-stage `Maximize(Σ score)`. Simplest, and reliably leaves one or two
  people with nothing. Keep it for comparison only.
* `MAXIMIN_THEN_SUM` — **default.** Stage 1 maximises `lo` with `lo ≤ score[d]` for all `d`.
  Stage 2 pins `lo` to its optimum and maximises `Σ score`.
* `LEXIMIN` — iteratively fix the current smallest score and re-solve on the remainder.
* `LEXICOGRAPHIC_TIERS` — stage *k* maximises the count of fulfilled tier-*k* wishes across the
  team, then constrains it (optionally with slack `ε`) before moving to tier *k+1*.

Implement staging as a reusable helper that takes a list of `(objective_expr, sense)` and threads
constraints between stages. Log each stage's objective value.

### Solution enumeration

Preference problems have many equal optima. After the final stage, re-solve with the objective
pinned to `optimum` (or `≥ 0.95 * optimum`, configurable) and collect solutions via
`CpSolverSolutionCallback`, capped at `max_solutions` (default 50) and `max_time_in_seconds`
(default 30). Deduplicate by a canonical signature: the frozenset of frozensets of dancer ids per
position — symmetry breaking makes positions comparable but the signature is the honest key.

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

Positions in the output are labelled A–H, not 1–8. The model treats them as interchangeable and
numbering them invites the team to read a ranking into the result that does not exist.

---

## 9. Persistence (`storage.py`)

YAML in `data/`, human-editable and diffable — the coach will hand-edit it, so preserve key order
and never rewrite the file with reordered content. `load_team(path) -> Team`,
`save_team(team, path)`. Ship a realistic `data/team.example.yaml` with 20 dancers, mixed flags and
a few tiers. No database.

---

## 10. Streamlit UI (`app/`)

Yes, a UI is worth it here: the survey data is fiddly, the coach is not going to edit YAML, and
comparing near-optimal solutions is inherently interactive.

* `Home.py` — load / create a team file, show a feasibility summary panel driven by §7.
* `1_Team.py` — dancer table with `st.data_editor`: name, role, `is_pole_position`,
  `needs_coaching`. The column headings the coach sees stay German ("Startanspruch",
  "Coachingbedarf") like every other user-facing string.
* `2_Umfrage.py` — pick a dancer, then per direction a dynamic list of tiers, each an
  `st.multiselect` over eligible dancers. "Tier hinzufügen" / "Tier entfernen" buttons.
  Live-validate rules 3 and 4 from §6 and show the conflict inline, in German.
* `3_Loesung.py` — solver config widgets (objective, weight scheme, veto tier, time limit),
  a run button, then the best solution as 8 cards, each showing the leaders and followers on the
  position with badges for fulfilled wishes and violated dislikes. Card headings stay German
  ("Herren" / "Damen").
* `4_Analyse.py` — per-dancer satisfaction table sorted ascending (the unhappiest first, that is
  the row the coach actually needs), plus a browser over the enumerated near-optimal solutions with
  a diff against the currently selected one.

Implementation notes:

* Team state lives in `st.session_state`, persisted to YAML on explicit save. No autosave.
* Wrap the solve call in `st.cache_data` keyed on a hash of `(Team, SolverConfig)`.
* Run the solve inside `st.spinner`; enforce the configured time limit so the UI cannot hang.
* Colour-code by satisfaction, but never by dancer name or role.

---

## 11. CLI (`cli.py`)

```
dancepartner check   data/team.yaml
dancepartner solve   data/team.yaml --objective maximin-then-sum --top 10 --json out.json
dancepartner explain data/team.yaml out.json --dancer lukas-b
```

The CLI is the reference interface and must reach full functionality at Milestone 2, before any UI
work starts.

---

## 12. Testing

* Unit tests per validator in §6, each asserting the specific error.
* Feasibility counting tests including the exact boundary cases (`n = 8`, `n = 16`, coaching count
  odd vs even).
* Hand-constructed micro-instances (3 positions, 6–8 dancers) with a known optimum, asserted by value.
* A constraint-verification helper `assert_valid(solution, team)` re-checking **every** hard
  constraint from §8 against the returned solution; call it in every solver test. The solver must
  never be trusted to have modelled what we think it modelled.
* The reification regression test from §8.
* A determinism test: same input plus fixed `random_seed` yields the same solution.
* Target ≥ 90 % coverage on `src/dancepartner/`, excluding `i18n.py`.

---

## 13. Milestones

Stop after each one and wait for my review.

1. **Core** — `model.py`, `feasibility.py`, `solver.py`, `scoring.py`, full test suite, `WEIGHTED_SUM`
   and `MAXIMIN_THEN_SUM` objectives. No CLI, no UI.
2. **CLI + storage** — `storage.py`, `cli.py`, `data/team.example.yaml`, CI workflow.
3. **Remaining objectives** — `LEXIMIN`, `LEXICOGRAPHIC_TIERS`, solution enumeration and
   deduplication, `explain` output.
4. **Streamlit UI** — all four pages, `i18n.py`.
5. **Polish** — README in German with a worked example, screenshots, performance notes on a
   realistic 24-dancer instance.

---

## 14. Non-goals and constraints

* Do not add authentication, multi-tenancy, or a database.
* Do not add a heuristic or genetic solver. The instance is tiny; CP-SAT solves it exactly and any
  fallback is dead code that will drift out of sync with the constraint set.
* Do not infer preferences the survey did not state — no transitive wishes, no "A likes B so B
  probably likes A", no clustering.
* Do not model height, appearance, choreography paths, or anything the coach did not ask for.
* Do not commit real survey data. `data/team.yaml` goes in `.gitignore`; only the example file is
  tracked.
* Ask me before changing anything in §3 or §6 — the glossary and the hard constraints are the parts
  the team has actually agreed on. (The English-vocabulary rename in §2.1 was agreed this way.)