# dancepartner

> Deutsche Version: [README.de.md](README.de.md)

Partnering a Latin formation team as an exact optimization problem.

Eight positions, around twenty dancers, and a team survey full of wishes that cannot all be
fulfilled at once. `dancepartner` computes which line-up serves the wishes best: not "good
enough", but provably optimal, using the CP-SAT solver from OR-Tools.

The tool decides nothing. It makes visible what the numbers allow: who stays unsatisfied, why,
and whether there is an alternative. The line-up is made by the coach.

## What the program models

Eight **positions**, labelled A through H. Letters on purpose: the positions are interchangeable,
and numbering them invites reading in a ranking that does not exist.

Every position is staffed in both roles, with one or two people per role. Two leaders *and* two
followers on one position make a **doubled position**. Because the squad rarely has equally many
leaders and followers, the limit applies per role: a position may carry two leaders and only one
follower.

| Term in the team | In the code and the team file | Meaning |
|---|---|---|
| Leader / Follower | `Role.LEADER` / `Role.FOLLOWER` | The two roles, fixed per person. |
| Position | index `p`, label A–H | One of 8 slots, unordered. |
| Doubled position | `is_doubled` | Two leaders and two followers on one position. |
| Pole position | `is_pole_position` | Must stand alone in their role. |
| Coaching need | `needs_coaching` | Must not stand alone in their role. |
| Desired partners | `desired_tiers` | Tiered wish lists, tier 1 the strongest. |
| Not-desired partners | `not_desired_tiers` | The same, inverted. |
| Team survey | `Survey` | One person's answers. |
| Partner assignment | `Solution` | One complete allocation. |

The code, the files, and the logs use exactly one vocabulary, the English one. Everything the
coach sees is available in English and German (see [Language](#language)).

Two properties decide the outcome and are easy to miss:

* **Wishes are directed.** Anna wishing for Lukas does not mean Lukas wishes for Anna. The
  program completes nothing by symmetry. Only hard **vetoes** act both ways, and necessarily so:
  two people either share a position or they do not.
* **Whoever does not answer scores 0 points** — and therefore sits at the top of the
  satisfaction table. Not a bug, but the honest statement that nothing is known about this
  person.

The full specification lives in [`SPEC.md`](SPEC.md).

## Installation

Python 3.11 or newer.

```bash
make install          # virtualenv, package with dev and ui extras, pre-commit hooks
```

By hand:

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'     # or '.[ui]' for just the interface
```

`streamlit` is not a runtime dependency but an extra. If you only need the command line, install
with `pip install -e .`. Conversely, `app/` can be deleted without the core missing anything.

## Quickstart

```bash
make ui                    # interface on http://localhost:8501
make ui PORT=8600          # or elsewhere
```

Or on the command line, which can do everything the interface can:

```bash
.venv/bin/dancepartner check   data/team.example.yaml
.venv/bin/dancepartner solve   data/team.example.yaml --top 3 --json out.json
.venv/bin/dancepartner explain data/team.example.yaml out.json --dancer lukas-b
```

`make` on its own lists all targets.

## Language

All user-facing output is English by default. `DANCEPARTNER_LANG=de` switches the CLI — help
texts included — to German; the Streamlit UI has a language selector in the sidebar. The Make
targets pass the variable through:

```bash
DANCEPARTNER_LANG=de .venv/bin/dancepartner check data/team.example.yaml
make cli DP_LANG=de
```

Team files are unaffected: the YAML vocabulary is English and identical in both languages.

## A worked example

`data/team.example.yaml` contains a fictional team: 20 dancers, 19 answered team surveys. The
outputs below are real.

### Pre-check

```console
$ dancepartner check data/team.example.yaml
20 dancers (9 leaders, 11 followers) on 8 positions A B C D E F G H.
19 of 20 have answered the team survey.

No countable obstacles found.
This does not guarantee a solution — it only means that no simple counting argument
rules one out. The solver has the final say.
```

`check` only tests what can be counted: do the role counts fit the positions? Are there enough
singly staffed positions for everyone with a pole-position claim? That is necessary but not
sufficient; solvability is only proven by the solver. The benefit: "5 leaders hold a pole
position but only 4 positions carry a single leader" says which checkbox has to go. A bare
INFEASIBLE says nothing.

### Solving

```console
$ dancepartner solve data/team.example.yaml --top 3
Status: OPTIMAL — 0.06 s, 8127 branches.
Objective in stages:
  maximin: 0 (maximized)
  sum: 55 (maximized)
  coupled: 4 (minimized)

3 equally good solution(s) found.

── Solution 1 of 3 (best)
   Total score 55, lowest individual score 0
Positions:
  Position A
     Leaders:   Lukas Brandt
     Followers: Anna Brenner
  Position C
     Leaders:   Tim Rothe
     Followers: Lena Fricke, Mia Thalmann
  …
  Position H
     Leaders:   Jan Hübner, Paul Mertens
     Followers: Hanna Zeller
```

Three things matter here.

**`maximin: 0` does not mean the computation failed.** Marie Günther did not submit a team
survey, so her score is 0 and so is the achievable minimum. The stage did its best; the floor
simply lies there.

**Scores are on the solver's ×2 scale.** With linear weighting a wish in tier *k* is initially
worth `K − k + 1`, where `K` is the instance's highest tier; the result is doubled so it can be
halved on a doubled position without rounding. In this team tier 2 is the deepest, so a
fulfilled tier-1 wish earns 4 points. That is why Lukas Brandt shows a 4 below.

**"3 equally good solutions" means exactly that.** All three reach 55 points. They are not
ranks 1 through 3, but three equally good answers the numbers cannot decide between. The coach
can.

### Asking why

```console
$ dancepartner explain data/team.example.yaml out.json --dancer lukas-b
(from solution 1 of 3)

Lukas Brandt (Leader) — Position A
  Score: 4
  On the same position: Anna Brenner
  Fulfilled wishes:
    Tier 1: Anna Brenner
  Unfulfilled wishes:
    Tier 2: Lena Fricke, Mia Thalmann
  Respected not-desired wishes:
    Tier 1: Emma Köhler

  This placement is the same in all 3 solutions — there is nothing to choose here.
```

The last sentence is the reason the program enumerates several solutions at all. A partner who
is the same in every optimal solution is not a decision the coach has to make. One who appears
in 3 of 20 solutions is. For this team, little remains to choose: Emma Köhler moves between
positions D and E, Lena Fricke between C and D. There are no further differences.

## The four objectives

The objective defines what "best" means. It changes the outcome, not the rules: hard constraints
always hold.

| `--objective` | Maximizes | When it makes sense |
|---|---|---|
| `weighted-sum` | the sum of all scores | Overall satisfaction counts, individual outliers are acceptable. |
| `maximin-then-sum` | first the lowest score, then the sum | The default. Raises the floor first, wastes nothing afterwards. |
| `leximin` | the sorted score vector, bottom up | The second- and third-unhappiest count too. |
| `lexicographic-tiers` | tier by tier, the number of fulfilled wishes | One tier-1 wish outweighs any number of tier-2 wishes. |

`maximin-then-sum` and `leximin` are not the same. Both raise the minimum first, but
`maximin-then-sum` then only maximizes the sum and may sacrifice the second-worst doing so.
`leximin` keeps working its way up and gives up total points for it if necessary. The case where
they measurably differ is pinned down in `tests/test_objectives.py::divergent_instance`.

Further knobs: `--weights` (linear or geometric), `--scope` (cross-role wishes only, or all),
`--veto-tier N` (not-desired wishes up to tier N become hard constraints, `0` turns them off),
`--top N`, `--near-optimal` and `--tier-slack`. `dancepartner solve --help` explains them all.

## Performance

Measured on an Apple Silicon laptop (arm64, macOS), Python 3.11.9, OR-Tools 9.15,
`num_workers = 1` for reproducibility, best of three runs. The times are reported by
`SolveResult.wall_time`, i.e. the sum over all solver stages. Both instances live in the
repository: `data/team.example.yaml` (20 dancers, tiers up to 2) and
`data/team.large.example.yaml` (24 dancers, tiers up to 3).

| Objective | 20 dancers | Branches | 24 dancers | Branches |
|---|---:|---:|---:|---:|
| `weighted-sum` | 0.04 s | 5,811 | **12.5 s** | 988,656 |
| `maximin-then-sum` | 0.05 s | 6,230 | **12.3 s** | 992,787 |
| `leximin` | 0.04 s | 887 | 0.17 s | 15,961 |
| `lexicographic-tiers` | 0.02 s | 565 | 0.05 s | 4,564 |

All four find the same total score on the large instance (101), but need very different amounts
of time to do so. And contrary to the obvious guess: `leximin` runs two stages per round and
looks expensive, yet is roughly 70 times faster here than the plain sum.

The reason is the burden of proof. `weighted-sum` has to show that no line-up with 102 points
exists, and a huge search space remains for that. `leximin`, by contrast, fixes the complete
sorted score vector round by round; each of those constraints cuts the search space down
drastically, so that in the end there is barely anything left to prove.

In practice:

* Up to about 20 dancers every objective finishes in under a tenth of a second.
  **Decide by content, not by speed.**
* If `maximin-then-sum` takes too long beyond that, `leximin` delivers the same result on this
  data in a fraction of the time — and is even the stronger statement.
* Enumeration costs almost nothing: `--top 50` instead of `--top 1` adds less than 0.2 s,
  because the second pass works on a model whose optima are already fixed.
* `--time-limit` is the emergency brake, not the normal case. If the solver runs into it, it
  reports `FEASIBLE` instead of `OPTIMAL`: the result is valid but not proven best. If it had no
  solution yet, none comes back (exit code 3).

To verify:

```bash
make cli TEAM=data/team.large.example.yaml DANCER=carolin-r
```

## The interface

`make ui` starts a home page and four working pages:

* **Home**: load, upload, or create a team file; pre-check; save.
* **Team**: the dancers as a table with name, role, pole position, coaching need.
* **Survey**: any number of tiers per person and direction; conflicts are reported immediately.
* **Solution**: configure the objective, solve, the eight positions as cards.
* **Analysis**: satisfaction sorted ascending, plus the comparison of the equally good
  solutions.

Saving happens only at the press of a button. PyYAML cannot preserve comments; an autosave would
silently strip them from a hand-maintained team file. Real data belongs in `data/team.yaml`: the
path is in `.gitignore`, and accidentally committed surveys would be a real problem.

## Development

```bash
make check      # everything CI checks too: ruff, mypy --strict, pytest, CLI
make test       # just the tests
make fmt        # format
```

The core lives in `src/dancepartner/` and never imports `streamlit`; the interface in `app/`
depends on the core, never the reverse. CI verifies this by moving `app/` aside, uninstalling
`streamlit`, and running `solve` once more.

Test coverage on `src/dancepartner/` sits at 100 % (the threshold is 90 %). More important than
the number: every solver test calls `tests/helpers.py::assert_result_valid`, which independently
re-checks every hard constraint. The solver is not trusted to have modelled what we believed we
were modelling.

The specification and the design decisions live in [`SPEC.md`](SPEC.md), the working rules for
contributors and agents in [`AGENTS.md`](AGENTS.md).

## License

MIT, see [`LICENSE`](LICENSE).
