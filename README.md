# dancepartner

> Deutsche Version: [README.de.md](README.de.md)

Partnering a Latin formation team as an exact optimization problem.

Eight positions, around twenty dancers, and a team survey full of wishes that cannot all be fulfilled at once.
`dancepartner` computes which line-up serves the wishes best: not "good enough", but provably optimal, using the CP-SAT
solver from OR-Tools.

The tool decides nothing. It makes visible what the numbers allow: who stays unsatisfied, why, and whether there is an
alternative. The line-up is made by the coach.

## What the program models

Eight **positions**, labelled A through H. Letters on purpose: the positions are interchangeable, and numbering them
invites reading in a ranking that does not exist.

Every position is staffed in both roles, with one or two people per role. Two leaders *and* two followers on one
position make a **doubled position**. Because the squad rarely has equally many leaders and followers, the limit applies
per role: a position may carry two leaders and only one follower.

| Term in the team     | In the code and the team file   | Meaning                                                                                                                                  |
|----------------------|---------------------------------|------------------------------------------------------------------------------------------------------------------------------------------|
| Leader / Follower    | `Role.LEADER` / `Role.FOLLOWER` | The two roles, fixed per person.                                                                                                         |
| Position             | index `p`, label A–H            | One of 8 slots, unordered.                                                                                                               |
| Doubled position     | `is_doubled`                    | Two leaders and two followers on one position.                                                                                           |
| Pole position        | `is_pole_position`              | Must stand alone in their role.                                                                                                          |
| Coaching need        | `needs_coaching`                | Must not stand alone in their role, and the same-role partner alongside must be experienced — two coaching needs never share a position. |
| Desired partners     | `desired_tiers`                 | Tiered wish lists, tier 1 the strongest.                                                                                                 |
| Not-desired partners | `not_desired_tiers`             | The same, inverted.                                                                                                                      |
| Coach rule           | `coach_constraints`             | A hard rule the coach sets: these people share one position (`together`), or no two of them do (`apart`).                                 |
| Team survey          | `Survey`                        | One person's answers.                                                                                                                    |
| Partner assignment   | `Solution`                      | One complete allocation.                                                                                                                 |

The code, the files, and the logs use exactly one vocabulary, the English one. Everything the coach sees is available in
English and German (see [Language](#language)).

Two properties decide the outcome and are easy to miss:

* **Wishes are directed.** Anna wishing for Lukas does not mean Lukas wishes for Anna. The program completes nothing by
  symmetry. Only hard **vetoes** act both ways, and necessarily so:
  two people either share a position or they do not.
* **A coach rule outranks the survey.** `together` puts people on one position and `apart` keeps
  them off it, whatever they wrote down. Unlike a veto it is not read out of anyone's answers, so
  the veto rank does not reach it. A rule names people and never a position letter — the positions
  stay interchangeable.
* **Whoever does not answer scores 0 points** — and therefore sits at the top of the satisfaction table. Not a bug, but
  the honest statement that nothing is known about this person.

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

`streamlit` is not a runtime dependency but an extra. If you only need the command line, install with
`pip install -e .`. Conversely, `app/` can be deleted without the core missing anything.

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

All user-facing output is English by default. `DANCEPARTNER_LANG=de` switches the CLI — help texts included — to German;
the Streamlit UI has a language selector in the sidebar. The Make targets pass the variable through:

```bash
DANCEPARTNER_LANG=de .venv/bin/dancepartner check data/team.example.yaml
make cli DP_LANG=de
```

Team files are unaffected: the YAML vocabulary is English and identical in both languages.

## A worked example

`data/team.example.yaml` contains a fictional team: 20 dancers, 19 answered team surveys. The outputs below are real.

### Pre-check

```console
$ dancepartner check data/team.example.yaml
20 dancers (9 leaders, 11 followers) on 8 positions A B C D E F G H.
19 of 20 have answered the team survey.

No countable obstacles found.
This does not guarantee a solution — it only means that no simple counting argument
rules one out. The solver has the final say.
```

`check` only tests what can be counted: do the role counts fit the positions? Are there enough singly staffed positions
for everyone with a pole-position claim? That is necessary but not sufficient; solvability is only proven by the solver.
The benefit: "5 leaders hold a pole position but only 4 positions carry a single leader" says which checkbox has to go.
A bare INFEASIBLE says nothing.

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

**`leximin.1.floor: 0` does not mean the computation failed.** Marie Günther did not submit a team survey, so her score
is 0 and so is the achievable minimum. The stage did its best; the floor simply lies there — and `leximin.1.count: 16`
is the point of the default objective: 16 of the 20 dancers are lifted *above* that floor, then round 2 raises the floor
under the rest to 2, and round 3 to 4.

**Scores count the best fulfilled wish, on the solver's ×2 scale.** A wish of rank *k* is worth `K − k + 1`, where `K`
is the deepest rank in the instance; the result is doubled so the doubled-position normalization can halve without
rounding. In this team the second wish is the deepest, so a fulfilled first wish earns 4 points — and by default that is
also the maximum: satisfaction saturates once the strongest wish is granted (`--aggregation best`). Whoever has their
top wish and no violated not-desired wish is 100 % satisfied, however many alternatives they listed. `--aggregation sum`
restores the older adding-up semantics.

**"2 equally good solutions" means exactly that.** Both reach 60 points. They are not ranks 1 and 2, but two equally
good answers the numbers cannot decide between. The coach can.

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

The last sentence is the reason the program enumerates several solutions at all. A partner who is the same in every
optimal solution is not a decision the coach has to make. One who appears in 3 of 20 solutions is. For this team,
exactly one choice remains: Leah Dorn dances either as David Lorenz' second follower on position F or beside Marie
Günther on position G.

On top of the shortlist, the program marks **exchange groups**: sets of dancers who can be permuted freely over their
positions — every arrangement keeps every hard constraint and the score vector, so a swap within a group costs nothing
at all. Their dancers carry the group's number (1️⃣, 2️⃣, …) right on the solution cards and in the analysis table. This
example team has none — Leah Dorn's move resizes two positions rather than swapping two dancers, which is exactly what
the solution browser is for.

## The four objectives

The objective defines what "best" means. It changes the outcome, not the rules: hard constraints always hold.

| `--objective`         | Maximizes                                    | When it makes sense                                              |
|-----------------------|----------------------------------------------|------------------------------------------------------------------|
| `weighted-sum`        | the sum of all scores                        | Overall satisfaction counts, individual outliers are acceptable. |
| `maximin-then-sum`    | first the lowest score, then the sum         | Raises the floor once, then stops caring about the worst-off.    |
| `leximin`             | the sorted score vector, bottom up           | **The default.** The second- and third-unhappiest count too.     |
| `lexicographic-tiers` | rank by rank, the number of fulfilled wishes | One first wish outweighs any number of second wishes.            |

`maximin-then-sum` and `leximin` are not the same. Both raise the minimum first, but
`maximin-then-sum` then only maximizes the sum and may sacrifice the second-worst doing so.
`leximin` keeps working its way up and gives up total points for it if necessary. The case where they measurably differ
is pinned down in `tests/test_objectives.py::divergent_instance`.

Further knobs: `--aggregation` (best fulfilled wish — the default — or sum of all fulfilled wishes), `--scope` (all
wishes — the default — or cross-role only), `--veto-tier N`
(not-desired wishes up to rank N become hard constraints, `0` turns them off), `--top N`,
`--near-optimal` and `--tier-slack`. `dancepartner solve --help` explains them all.

`--near-optimal` widens the shortlist by a percentage of each stage optimum, so it only bites under `maximin-then-sum`,
whose `sum` stage is large enough. Leximin's stage optima are single-dancer scores, where a few percent rounds to
nothing.

## Performance

Measured on an Apple Silicon laptop (arm64, macOS), Python 3.11.9, OR-Tools 9.15,
`num_workers = 1` for reproducibility, best of three runs. The times are reported by
`SolveResult.wall_time`, i.e. the sum over all solver stages. Both instances live in the repository:
`data/team.example.yaml` (20 dancers, wishes down to rank 2) and
`data/team.large.example.yaml` (24 dancers, down to rank 3).

With the default best-wish aggregation, every objective is fast on both instances:

| Objective             | 20 dancers | Branches | 24 dancers | Branches |
|-----------------------|-----------:|---------:|-----------:|---------:|
| `weighted-sum`        |     0.01 s |      826 |     0.03 s |    3,037 |
| `maximin-then-sum`    |     0.01 s |    1,108 |     0.04 s |    3,751 |
| `leximin`             |     0.03 s |      929 |     0.05 s |    3,710 |
| `lexicographic-tiers` |     0.01 s |      814 |     0.04 s |    2,452 |

The hard case is the summed aggregation (`--aggregation sum`) on the large instance:

| Objective, `--aggregation sum` | 24 dancers |  Branches |
|--------------------------------|-----------:|----------:|
| `weighted-sum`                 | **11.8 s** | 1,007,227 |
| `maximin-then-sum`             | **11.9 s** | 1,011,225 |
| `leximin`                      |     0.16 s |    15,380 |
| `lexicographic-tiers`          |     0.05 s |     4,306 |

All four find the same summed total there (101), but need very different amounts of time to do so. And contrary to the
obvious guess: `leximin` runs two stages per round and looks expensive, yet is roughly 70 times faster here than the
plain sum.

The reason is the burden of proof. Under `sum`, `weighted-sum` has to show that no line-up with 102 points exists, and a
huge search space remains for that. `leximin`, by contrast, fixes the complete sorted score vector round by round; each
of those constraints cuts the search space down drastically, so that in the end there is barely anything left to prove.
The best-wish aggregation is fast for the same reason from the other side: scores take far fewer distinct values, so the
bounds close quickly.

In practice:

* With the default aggregation every objective finishes in well under a tenth of a second on both instances. **Decide by
  content, not by speed.**
* Under `--aggregation sum`, if `maximin-then-sum` takes too long, `leximin` delivers the same total on this data in a
  fraction of the time — and is even the stronger statement.
* Enumeration costs almost nothing: `--top 50` instead of `--top 1` adds less than 0.2 s, because the second pass works
  on a model whose optima are already fixed.
* `--time-limit` is the emergency brake, not the normal case. If the solver runs into it, it reports `FEASIBLE` instead
  of `OPTIMAL`: the result is valid but not proven best. If it had no solution yet, none comes back (exit code 3).

### The two backends

The figures above are CP-SAT, the default. HiGHS solves the same model as a MILP and is what the browser build uses,
because OR-Tools has no WebAssembly wheel. Same instances, same method, `--backend` to pick:

| Objective, default aggregation | cpsat 20 | highs 20 | cpsat 24 | highs 24 |
|--------------------------------|---------:|---------:|---------:|---------:|
| `leximin`                      |   0.03 s |   0.08 s |   0.06 s |   0.53 s |
| `weighted-sum`                 |   0.01 s |   0.05 s |   0.03 s |   0.68 s |
| `maximin-then-sum`             |   0.02 s |   0.06 s |   0.05 s |   0.47 s |
| `lexicographic-tiers`          |   0.02 s |   0.06 s |   0.04 s |   1.24 s |

| Objective, `--aggregation sum` | cpsat 20 | highs 20 | cpsat 24 | highs 24 |
|--------------------------------|---------:|---------:|---------:|---------:|
| `leximin`                      |   0.05 s |   0.18 s |   0.18 s |   4.09 s |
| `weighted-sum`                 |   0.05 s |   1.36 s | 13.1 s \* |  140 s \* |
| `maximin-then-sum`             |   0.06 s |   1.91 s | 12.4 s \* |  146 s \* |
| `lexicographic-tiers`          |   0.03 s |   0.09 s |   0.06 s |   2.82 s |

\* Single runs of one measurement, not best of three, and the HiGHS side needs `--time-limit` raised above its
30 s default. Both columns of a starred row come from the same run, so the comparison within it is fair.

Both solvers reach the same answer everywhere in both tables. HiGHS is a factor of three to thirty slower, and at the
default aggregation that is the difference between instant and still instant. Enumeration holds up better than
expected: `--top 50` on the 20-dancer instance costs 0.11 s against CP-SAT's 0.04 s, even though HiGHS has no solution
pool and has to re-solve with a no-good cut per assignment — the model is so tightly pinned by then that each re-solve
is nearly free.

The two starred cells are the honest part. They are the same combinations the notes above already single out as
pathological, and the gap widens there from a factor of thirty to a factor of eleven on top of an already slow solve.
Under `--aggregation sum` on the larger instance, use `leximin` — which is the stronger statement anyway, and the
default.

To verify:

```bash
make cli TEAM=data/team.large.example.yaml DANCER=carolin-r
```

## The interface

`make ui` starts a home page and four working pages:

* **Home**: upload or create a team, or load the example; pre-check; download the team as YAML.
* **Team**: the dancers as a table with name, role, pole position, coaching need — and below it the coach rules,
  which name dancers from that table.
* **Survey**: any number of ranks per person and direction; conflicts are reported immediately.
* **Solution**: configure the objective, solve, the eight positions as cards — dancers who can be swapped freely at zero
  cost are numbered 1️⃣, 2️⃣, …
* **Analysis**: satisfaction sorted ascending, the exchange groups of the selected solution, plus the comparison of the
  equally good solutions.

Saving happens only at the press of a button, and takes the form of a download — the app has no writable path of its own
once it is served to a browser. PyYAML cannot preserve comments; an autosave would silently strip them from a
hand-maintained team file.

What the app *does* keep by itself is a **draft**: the team as it stands right now, so that a reload does not cost you
an evening of survey entry. A draft is not a save — it never clears the unsaved-changes warning, and it is never written
to the file the team came from. In the browser version it lives in that browser's IndexedDB; on a server it lives in
memory, keyed by the
`?draft=` token in the URL. Neither one reaches a disk.

Loading a team keeps the previous one, so trying the example does not throw away what you had. Editing overwrites the
current version rather than piling up another; the last ten are listed under "Earlier versions" on the start page, with
a button back to each. That list is there rather than the browser's back button because Streamlit cannot see which
version a back press points at ([streamlit#13963](https://github.com/streamlit/streamlit/issues/13963)).

Real data belongs in `data/team.yaml`: the path is in `.gitignore`, and accidentally committed surveys would be a real
problem.

## Deployment

The same interface runs three ways, and all three can compute an assignment — the browser one included. It solves with
[HiGHS](https://highs.dev) rather than OR-Tools, because OR-Tools has no WebAssembly build and HiGHS does. Both produce
the same answer; the [specification](SPEC.md) explains how that is enforced.

|                                          | `make ui` locally    | Browser (GitHub Pages)          | Server (Docker)               |
|------------------------------------------|----------------------|---------------------------------|-------------------------------|
| Load, create, upload, download a team    | ✅                   | ✅                              | ✅                            |
| Edit the roster and the survey           | ✅                   | ✅                              | ✅                            |
| Feasibility pre-check                    | ✅                   | ✅                              | ✅                            |
| **Compute an assignment**                | ✅ CP-SAT            | ✅ HiGHS                        | ✅ CP-SAT                     |
| **Analysis, exchange groups, shortlist** | ✅                   | ✅                              | ✅                            |
| The CLI                                  | ✅                   | ❌                              | ✅ via `docker exec`          |
| Works offline                            | ✅                   | ✅ after the first visit        | ❌ needs the server           |
| The language setting sticks              | ✅ in the URL        | ✅ across fresh visits          | ✅ in the URL                 |
| A reload keeps the team                  | ✅ in memory         | ✅ IndexedDB, on the device     | ✅ in memory, via `?draft=`   |
| Earlier versions to go back to | ✅ this session | ✅ last 10, across reloads | ✅ last 10, this session |
| Survey data leaves the machine           | no                   | no — it never leaves the device | yes, to your server           |
| What a coach has to install              | a Python environment | nothing, just a URL             | nothing, a URL and a password |

Where a build cannot do something it says so on the page, with the reason. Nothing is hidden.

### The browser version

```bash
make wasm-serve     # build and serve on http://localhost:8000
make wasm           # just build, into wasm/dist, for the Pages base path
```

`.github/workflows/pages.yml` publishes it on every push to `main`. The first load pulls roughly 30 MB of Pyodide and
takes a few seconds, behind a loading screen that says what is happening — a blank page is indistinguishable from a
broken deploy, and "Unpacking archives" is not addressed to a dance coach.

A service worker caches that 30 MB on the way past, so a second visit is quick and works with no network at all. It
installs as a web app, with a manifest and real icons. Deep links work too: `/survey` reloads onto the survey page
rather than a 404, on Pages and under `make wasm-serve` alike.

### The server version

```bash
cp docker/.env.example docker/.env     # then fill it in
docker run --rm caddy:2-alpine caddy hash-password --plaintext 'the-password'
make docker-up
```

Caddy terminates TLS and handles authentication — basic auth as a placeholder, with the Caddyfile marking where OIDC
goes. Authentication never moves into the app. The container runs as a non-root user on a read-only filesystem: survey
answers live in its memory and never reach its disk.

The environment variables are documented in `docker/.env.example`; none of them has a real value in the repository.

## Development

```bash
make check      # everything CI checks too: ruff, mypy --strict, pytest, CLI
make test       # just the tests
make fmt        # format
```

The core lives in `src/dancepartner/` and never imports `streamlit`; the interface in `app/`
depends on the core, never the reverse. CI verifies this by moving `app/` aside, uninstalling
`streamlit`, and running `solve` once more.

Test coverage on `src/dancepartner/` sits at 100 %, measured by `make cov-both` — the suite run against each solver
backend and combined, because neither run alone can reach it: whichever backend is idle looks dead. `make check` keeps
a 90 % gate on the single-backend run. More important than the number: every solver test calls
`tests/helpers.py::assert_result_valid`, which independently re-checks every hard constraint. Neither solver is trusted
to have modelled what we believed we were modelling, and running the same tests against both is how they are held to
the same answer.

### Adding a dependency

It has to clear three gates, not one:

1. `pyproject.toml`, then re-freeze `requirements-dev.txt`. That is what CI and the Docker image both pin against.
2. **Can it run in the browser?** If `src/dancepartner/` imports it outside a backend module, it must exist in the
   Pyodide distribution stlite loads. Check `wasm/pyodide-lock.trimmed.json`, add it to `wasm/requirements-wasm.txt`
   pinned to *exactly* that version, and `tests/test_wasm_deps.py` will confirm it. A pure-Python `py3-none-any` wheel
   from PyPI works too; a compiled extension does not, unless Pyodide builds it.
3. **If it cannot**, it gets the OR-Tools treatment: confined to one module, reached only through a dispatcher that
   imports it lazily, excluded from the bundle by `build_static.SERVER_ONLY`, and gated in the UI behind a capability
   flag. Never a bare module-level import in something the browser pages need.

The specification and the design decisions live in [`SPEC.md`](SPEC.md), the working rules for contributors and agents
in [`AGENTS.md`](AGENTS.md).

## License

MIT, see [`LICENSE`](LICENSE).
