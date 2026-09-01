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
| Coaching need | `needs_coaching` | Must not stand alone in their role, and the same-role partner alongside must be experienced — two coaching needs never share a position. |
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
Status: OPTIMAL — 0.03 s, 934 branches.
Objective in stages:
  leximin.1.floor: 0 (maximized)
  leximin.1.count: 16 (maximized)
  leximin.2.floor: 2 (maximized)
  leximin.2.count: 14 (maximized)
  leximin.3.floor: 4 (maximized)
  leximin.3.count: 0 (maximized)
  coupled: 2 (minimized)

2 equally good solution(s) found.

── Solution 1 of 2 (best)
   Total score 60, lowest individual score 0
Positions:
  Position A
     Leaders:   Lukas Brandt
     Followers: Anna Brenner
  Position C
     Leaders:   Tim Rothe
     Followers: Lena Fricke, Mia Thalmann
  …
  Position H  (doubled)
     Leaders:   Jan Hübner, Paul Mertens
     Followers: Emma Köhler, Hanna Zeller
```

Three things matter here.

**`leximin.1.floor: 0` does not mean the computation failed.** Marie Günther did not submit a
team survey, so her score is 0 and so is the achievable minimum. The stage did its best; the
floor simply lies there — and `leximin.1.count: 16` is the point of the default objective: 16 of
the 20 dancers are lifted *above* that floor, then round 2 raises the floor under the rest to 2,
and round 3 to 4.

**Scores count the best fulfilled wish, on the solver's ×2 scale.** A wish of rank *k* is
worth `K − k + 1`, where `K` is the deepest rank in the instance; the result is doubled so the
doubled-position normalization can halve without rounding. In this team the second wish is the
deepest, so a fulfilled first wish earns 4 points — and by default that is also the
maximum: satisfaction saturates once the strongest wish is granted (`--aggregation best`).
Whoever has their top wish and no violated not-desired wish is 100 % satisfied, however many
alternatives they listed. `--aggregation sum` restores the older adding-up semantics.

**"2 equally good solutions" means exactly that.** Both reach 60 points. They are not ranks
1 and 2, but two equally good answers the numbers cannot decide between. The coach can.

### Asking why

```console
$ dancepartner explain data/team.example.yaml out.json --dancer lukas-b
(from solution 1 of 2)

Lukas Brandt (Leader) — Position A
  Score: 4
  Satisfaction: 100 %
  On the same position: Anna Brenner
  Fulfilled wishes:
    Wish 1: Anna Brenner
  Unfulfilled wishes:
    Wish 2: Lena Fricke, Mia Thalmann
  Respected not-desired wishes:
    No-go 1: Emma Köhler

  This placement is the same in all 2 solutions — there is nothing to choose here.
```

The last sentence is the reason the program enumerates several solutions at all. A partner who
is the same in every optimal solution is not a decision the coach has to make. One who appears
in 3 of 20 solutions is. For this team, exactly one choice remains: Leah Dorn dances either as
David Lorenz' second follower on position F or beside Marie Günther on position G.

On top of the shortlist, the program marks **exchange groups**: sets of dancers who can be
permuted freely over their positions — every arrangement keeps every hard constraint and the
score vector, so a swap within a group costs nothing at all. Their dancers carry the group's
number (1️⃣, 2️⃣, …) right on the solution cards and in the analysis table. This example team
has none — Leah Dorn's move resizes two positions rather than swapping two dancers, which is
exactly what the solution browser is for.

## The four objectives

The objective defines what "best" means. It changes the outcome, not the rules: hard constraints
always hold.

| `--objective` | Maximizes | When it makes sense |
|---|---|---|
| `weighted-sum` | the sum of all scores | Overall satisfaction counts, individual outliers are acceptable. |
| `maximin-then-sum` | first the lowest score, then the sum | Raises the floor once, then stops caring about the worst-off. |
| `leximin` | the sorted score vector, bottom up | **The default.** The second- and third-unhappiest count too. |
| `lexicographic-tiers` | rank by rank, the number of fulfilled wishes | One first wish outweighs any number of second wishes. |

`maximin-then-sum` and `leximin` are not the same. Both raise the minimum first, but
`maximin-then-sum` then only maximizes the sum and may sacrifice the second-worst doing so.
`leximin` keeps working its way up and gives up total points for it if necessary. The case where
they measurably differ is pinned down in `tests/test_objectives.py::divergent_instance`.

Further knobs: `--aggregation` (best fulfilled wish — the default — or sum of all fulfilled
wishes), `--scope` (all wishes — the default — or cross-role only), `--veto-tier N`
(not-desired wishes up to rank N become hard constraints, `0` turns them off), `--top N`,
`--near-optimal` and `--tier-slack`. `dancepartner solve --help` explains them all.

`--near-optimal` widens the shortlist by a percentage of each stage optimum, so it only bites
under `maximin-then-sum`, whose `sum` stage is large enough. Leximin's stage optima are
single-dancer scores, where a few percent rounds to nothing.

## Performance

Measured on an Apple Silicon laptop (arm64, macOS), Python 3.11.9, OR-Tools 9.15,
`num_workers = 1` for reproducibility, best of three runs. The times are reported by
`SolveResult.wall_time`, i.e. the sum over all solver stages. Both instances live in the
repository: `data/team.example.yaml` (20 dancers, wishes down to rank 2) and
`data/team.large.example.yaml` (24 dancers, down to rank 3).

With the default best-wish aggregation, every objective is fast on both instances:

| Objective | 20 dancers | Branches | 24 dancers | Branches |
|---|---:|---:|---:|---:|
| `weighted-sum` | 0.01 s | 826 | 0.03 s | 3,037 |
| `maximin-then-sum` | 0.01 s | 1,108 | 0.04 s | 3,751 |
| `leximin` | 0.03 s | 929 | 0.05 s | 3,710 |
| `lexicographic-tiers` | 0.01 s | 814 | 0.04 s | 2,452 |

The hard case is the summed aggregation (`--aggregation sum`) on the large instance:

| Objective, `--aggregation sum` | 24 dancers | Branches |
|---|---:|---:|
| `weighted-sum` | **11.8 s** | 1,007,227 |
| `maximin-then-sum` | **11.9 s** | 1,011,225 |
| `leximin` | 0.16 s | 15,380 |
| `lexicographic-tiers` | 0.05 s | 4,306 |

All four find the same summed total there (101), but need very different amounts of time to do
so. And contrary to the obvious guess: `leximin` runs two stages per round and looks expensive,
yet is roughly 70 times faster here than the plain sum.

The reason is the burden of proof. Under `sum`, `weighted-sum` has to show that no line-up with
102 points exists, and a huge search space remains for that. `leximin`, by contrast, fixes the
complete sorted score vector round by round; each of those constraints cuts the search space
down drastically, so that in the end there is barely anything left to prove. The best-wish
aggregation is fast for the same reason from the other side: scores take far fewer distinct
values, so the bounds close quickly.

In practice:

* With the default aggregation every objective finishes in well under a tenth of a second on
  both instances. **Decide by content, not by speed.**
* Under `--aggregation sum`, if `maximin-then-sum` takes too long, `leximin` delivers the same
  total on this data in a fraction of the time — and is even the stronger statement.
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

* **Home**: upload or create a team, or load the example; pre-check; download the team as YAML.
* **Team**: the dancers as a table with name, role, pole position, coaching need.
* **Survey**: any number of ranks per person and direction; conflicts are reported immediately.
* **Solution**: configure the objective, solve, the eight positions as cards — dancers who can
  be swapped freely at zero cost are numbered 1️⃣, 2️⃣, …
* **Analysis**: satisfaction sorted ascending, the exchange groups of the selected solution,
  plus the comparison of the equally good solutions.

Saving happens only at the press of a button, and takes the form of a download — the app has no
writable path of its own once it is served to a browser. PyYAML cannot preserve comments; an
autosave would silently strip them from a hand-maintained team file. Real data belongs in
`data/team.yaml`: the path is in `.gitignore`, and accidentally committed surveys would be a real
problem.

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
