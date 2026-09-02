"""The HiGHS backend: the same model as :mod:`dancepartner.cpsat`, written as a MILP.

Why a second backend at all: ortools has no WebAssembly wheel and highspy does, so this is the
only one of the two that can run in the browser build (SPEC.md 14.2). It is deliberately a
faithful mirror of ``cpsat.py`` -- same stage names, same order, same pinning rules -- so the
two can be diffed against each other, and so the cross-backend test can assert they reach the
same stage values.

What changes is only how the logic is expressed. CP-SAT states implications directly with
``only_enforce_if``; a MILP has to linearize them:

* ``together`` becomes the standard AND: ``b <= x_d``, ``b <= x_e``, ``b >= x_d + x_e - 1``.
  All three rows are mandatory -- with only the first two, and negative weights in the
  objective, the solver sets ``b = 0`` for a pair that does share a position and erases the
  dislike penalty. That is the same trap the CP-SAT reification has, and the same test guards
  it (``tests/test_solver.py::test_reification_cannot_erase_dislike``).
* ``doubled`` needs no reification at all here: the role count is already confined to ``{1, 2}``,
  so ``sum(x) == 1 + doubled`` defines the flag and the bound in one equality.
* Pole position and coaching need reduce to the same flag: ``doubled + x <= 1`` and
  ``doubled >= x``. No big-M.
* ``max`` (the ``BEST`` aggregation) needs a selector: ``best >= c_i v_i`` for every operand
  plus ``best <= c_i v_i + M(1 - y_i)`` with ``sum y_i = 1``.
* The half-scaling of cross-role weights is a product of a binary and a linear expression, so
  it takes four big-M rows.

Enumeration is where the two genuinely differ. CP-SAT enumerates inside one search; HiGHS has
no solution pool, so this re-solves with a no-good cut per solution found. See
:func:`_enumerate`.
"""

from __future__ import annotations

import logging
from collections.abc import Generator
from dataclasses import dataclass, field
from typing import Final

from ._milp import Expr, Model
from .feasibility import check_feasibility, together_components, veto_pairs
from .model import Objective, Role, ScoreAggregation, SolverConfig, Team
from .results import (
    InfeasibleInstanceError,
    Sense,
    SolveResult,
    Stage,
    StageResult,
    ranking_key,
)
from .scoring import Solution, build_solution, build_weights, scored_pairs

__all__ = ["NAME", "solve"]

logger = logging.getLogger(__name__)

NAME = "highs"
"""Backend identifier, as recorded on :attr:`dancepartner.results.SolveResult.backend`."""

_Stage = Stage[Expr]
StageSource = Generator[_Stage, int, None]


@dataclass
class _Vars:
    """The columns of one built model, by the same names ``cpsat._Vars`` uses."""

    x: dict[tuple[str, int], int]
    together: dict[frozenset[str], Expr]
    doubled: dict[tuple[Role, int], int]
    score: dict[str, Expr]
    mismatch: dict[int, int] = field(default_factory=dict)
    score_bound: int = 0


# -- entry point --------------------------------------------------------------------------


def solve(
    team: Team,
    config: SolverConfig | None = None,
    *,
    skip_precheck: bool = False,
    break_symmetry: bool = True,
) -> SolveResult:
    """Solve the assignment problem with HiGHS. See :func:`dancepartner.solver.solve`.

    Raises:
        InfeasibleInstanceError: The counting pre-checks found an obstruction.
    """
    config = config or SolverConfig()
    if not skip_precheck:
        issues = check_feasibility(team, config)
        if issues:
            raise InfeasibleInstanceError(issues)

    model = _new_model(config)
    variables = _build_model(model, team, config, break_symmetry=break_symmetry)
    source = _stage_source(model, team, config, variables)
    stages, status, wall_time, nodes = _run_stages(model, source)

    if status not in ("OPTIMAL", "FEASIBLE"):
        return SolveResult(
            backend=NAME,
            status=status,
            solutions=[],
            stages=stages,
            wall_time=wall_time,
            num_branches=nodes,
        )

    if config.max_solutions == 1:
        return SolveResult(
            backend=NAME,
            status=status,
            solutions=[build_solution(team, config, _groups(model, team, variables))],
            stages=stages,
            wall_time=wall_time,
            num_branches=nodes,
        )

    solutions, truncated, extra_time, extra_nodes = _enumerate(
        team, config, stages, break_symmetry=break_symmetry
    )
    return SolveResult(
        backend=NAME,
        status=status,
        solutions=solutions,
        stages=stages,
        truncated=truncated,
        wall_time=wall_time + extra_time,
        num_branches=nodes + extra_nodes,
    )


def _new_model(config: SolverConfig) -> Model:
    return Model(
        seed=config.random_seed,
        time_limit=config.max_time_in_seconds,
        log=config.log_search_progress,
    )


def _groups(model: Model, team: Team, variables: _Vars) -> list[list[str]]:
    """Read the dancer ids per position out of a solved model."""
    return [
        [d.id for d in team.dancers if model.is_set(variables.x[(d.id, p)])] for p in team.positions
    ]


# -- running the stages -------------------------------------------------------------------


def _run_stages(model: Model, source: StageSource) -> tuple[list[StageResult], str, float, int]:
    """Optimise each stage in turn, pinning its optimum before the next one is built.

    Structurally identical to ``cpsat._run_stages``; see the reasoning there. The one
    difference is bookkeeping: HiGHS reports the run time of its most recent solve, so the
    totals are accumulated per stage rather than read once at the end.
    """
    results: list[StageResult] = []
    history: list[_Stage] = []
    wall_time = 0.0
    nodes = 0
    # Captured per solve rather than read at the end: `_lock_in` adds rows after the last one,
    # and HiGHS invalidates its model status as soon as the model changes.
    status = "UNKNOWN"
    try:
        stage = next(source)
    except StopIteration:  # pragma: no cover -- every objective yields at least one stage
        return results, status, wall_time, nodes

    while True:
        if stage.tie_break:
            results = _lock_in(model, history, results)
        ok = model.optimize(stage.expr, maximize=stage.sense is Sense.MAXIMIZE)
        wall_time += model.wall_time
        nodes += model.num_nodes
        status = model.status_name
        if not ok:
            logger.warning("stage %s ended with status %s", stage.name, status)
            source.close()
            return results, status, wall_time, nodes

        value = model.value(stage.expr)
        logger.info("stage %s (%s) = %d", stage.name, stage.sense.value, value)
        results.append(StageResult(name=stage.name, sense=stage.sense, value=value))
        _pin(model, stage, value, extra_slack=0)
        history.append(stage)
        try:
            stage = source.send(value)
        except StopIteration:
            break
    return _lock_in(model, history, results), status, wall_time, nodes


def _lock_in(model: Model, history: list[_Stage], results: list[StageResult]) -> list[StageResult]:
    """Stop a tie-break stage from spending an earlier stage's slack. See ``cpsat._lock_in``."""
    locked = list(results)
    for index, stage in enumerate(history):
        if stage.slack == 0:
            continue
        achieved = model.value(stage.expr)
        if stage.sense is Sense.MAXIMIZE:
            model.add(stage.expr, lo=achieved)
        else:
            model.add(stage.expr, hi=achieved)
        locked[index] = results[index].model_copy(update={"locked_at": achieved})
        logger.info("locked stage %s at %d", stage.name, achieved)
    return locked


def _pin(model: Model, stage: _Stage, value: int, extra_slack: int) -> None:
    """Constrain a stage's expression to its achieved optimum, within slack."""
    slack = stage.slack + extra_slack
    if stage.sense is Sense.MAXIMIZE:
        if stage.surrogate:
            model.equal(stage.expr, value - slack)
        else:
            model.add(stage.expr, lo=value - slack)
    else:
        model.add(stage.expr, hi=value + slack)


def _slack_for(value: int, ratio: float) -> int:
    """How far below a stage optimum the enumeration still accepts. See ``cpsat._slack_for``."""
    if ratio >= 1.0:
        return 0
    return int((1.0 - ratio) * abs(value))


# -- model construction ------------------------------------------------------------------


def _build_model(model: Model, team: Team, config: SolverConfig, *, break_symmetry: bool) -> _Vars:
    x = {(dancer.id, p): model.binary() for dancer in team.dancers for p in team.positions}

    # 1. Every dancer occupies exactly one position.
    for dancer in team.dancers:
        model.equal(Expr.sum([Expr.of(x[(dancer.id, p)]) for p in team.positions]), 1)

    # 2. Per position and per role: one or two dancers, the two roles independent. The count is
    #    confined to {1, 2} and the "doubled" flag defined by the same equality -- a MILP
    #    convenience CP-SAT does not get, where the flag needs its own reification.
    doubled: dict[tuple[Role, int], int] = {}
    for role in Role:
        members = team.by_role(role)
        for p in team.positions:
            flag = model.binary()
            occupants = Expr.sum([Expr.of(x[(d.id, p)]) for d in members])
            model.equal(occupants - Expr.of(flag), 1)
            doubled[(role, p)] = flag

    # 3./4. Pole position and coaching need, on the position the dancer occupies. Both reduce
    #       to the doubled flag, so neither needs a big-M.
    for dancer in team.dancers:
        for p in team.positions:
            own = Expr.of(doubled[(dancer.role, p)])
            if dancer.is_pole_position:
                model.add(own + Expr.of(x[(dancer.id, p)]), hi=1)
            elif dancer.needs_coaching:
                model.add(own - Expr.of(x[(dancer.id, p)]), lo=0)

    # 5. At most one dancer with a coaching need per role per position.
    for role in Role:
        coaching = [d for d in team.by_role(role) if d.needs_coaching]
        if len(coaching) > 1:
            for p in team.positions:
                model.add(Expr.sum([Expr.of(x[(d.id, p)]) for d in coaching]), hi=1)

    together = {pair: _reify_together(model, x, team, pair) for pair in scored_pairs(team, config)}

    # 6. Hard vetoes.
    for pair in veto_pairs(team, config):
        model.equal(together[pair], 0)

    # 7. The coach's own rules. See ``cpsat._build_model``: stated on x, label-free, so the
    #    canonical numbering below stays valid. Two rows of pure 0/1 equality, no big-M.
    for component in together_components(team):
        anchor, *rest = sorted(component)
        for other in rest:
            for p in team.positions:
                model.equal(Expr.of(x[(anchor, p)]) - Expr.of(x[(other, p)]), 0)
    for group in team.coach_constraints.apart:
        for p in team.positions:
            model.add(Expr.sum([Expr.of(x[(i, p)]) for i in sorted(group)]), hi=1)

    if break_symmetry:
        _break_symmetry(model, x, team)

    score, score_bound = _build_scores(model, x, together, doubled, team, config)
    mismatch = _build_mismatch(model, doubled, team) if config.prefer_coupled else {}
    return _Vars(
        x=x,
        together=together,
        doubled=doubled,
        score=score,
        mismatch=mismatch,
        score_bound=score_bound,
    )


def _reify_together(
    model: Model, x: dict[tuple[str, int], int], team: Team, pair: frozenset[str]
) -> Expr:
    """Reify "these two dancers share a position", as the standard AND linearization.

    The third row is what stops the solver zeroing the flag for a pair that *does* share a
    position in order to dodge a negative weight. All three are mandatory.
    """
    d, e = sorted(pair)
    per_position: list[Expr] = []
    for p in team.positions:
        b = Expr.of(model.binary())
        xd, xe = Expr.of(x[(d, p)]), Expr.of(x[(e, p)])
        model.add(b - xd, hi=0)
        model.add(b - xe, hi=0)
        model.add(b - xd - xe, lo=-1)
        per_position.append(b)
    # Each dancer sits on exactly one position, so at most one term can be 1 and the sum is
    # already a 0/1 quantity; it needs no column of its own.
    return Expr.sum(per_position)


def _break_symmetry(model: Model, x: dict[tuple[str, int], int], team: Team) -> None:
    """Canonical position numbering over the leaders. See ``cpsat._break_symmetry``."""
    leaders = team.by_role(Role.LEADER)
    for i, leader in enumerate(leaders):
        for p in team.positions:
            if p == 0:
                continue
            earlier = [Expr.of(x[(other.id, p - 1)]) for other in leaders[:i]]
            if earlier:
                model.add(Expr.of(x[(leader.id, p)]) - Expr.sum(earlier), hi=0)
            else:
                model.equal(Expr.of(x[(leader.id, p)]), 0)


def _build_scores(
    model: Model,
    x: dict[tuple[str, int], int],
    together: dict[frozenset[str], Expr],
    doubled: dict[tuple[Role, int], int],
    team: Team,
    config: SolverConfig,
) -> tuple[dict[str, Expr], int]:
    """One score expression per dancer, on ``config.score_scale``. See ``cpsat._build_scores``."""
    weights = build_weights(team, config)
    by_id = team.dancers_by_id
    scale = config.score_scale

    cross_terms: dict[str, list[tuple[int, Expr]]] = {d.id: [] for d in team.dancers}
    same_terms: dict[str, list[tuple[int, Expr]]] = {d.id: [] for d in team.dancers}
    for (source, target), weight in weights.items():
        variable = together[frozenset((source, target))]
        bucket = cross_terms if by_id[source].role is not by_id[target].role else same_terms
        bucket[source].append((weight, variable))

    bound = sum(abs(weight) for weight in weights.values()) * scale + 1
    score: dict[str, Expr] = {}
    for dancer in team.dancers:
        cross = cross_terms[dancer.id]
        same = same_terms[dancer.id]

        best_fulfilled: Expr = Expr()
        if config.aggregation is ScoreAggregation.BEST:
            positive = [(w, v) for w, v in (*cross, *same) if w > 0]
            cross = [(w, v) for w, v in cross if w < 0]
            same = [(w, v) for w, v in same if w < 0]
            if positive:
                best_fulfilled = _build_best(model, positive, scale)

        raw_cross = Expr.sum([v * w for w, v in cross])
        raw_same = Expr.sum([v * w for w, v in same])

        if not config.normalize_double or not cross:
            score[dancer.id] = best_fulfilled + raw_cross * scale + raw_same * scale
            continue

        partner_doubled = _partner_doubled(model, x, doubled, team, dancer.id)
        scaled_cross = Expr.of(model.integer(-bound, bound))
        # scaled_cross == raw_cross when the opposite role is doubled here, scale * raw_cross
        # otherwise. A product of a binary and a linear expression, so four big-M rows; CP-SAT
        # says the same thing with two enforced equalities.
        #
        # Both sides of the switch live in [-bound, bound], so their difference cannot exceed
        # 2 * bound and this M is provably slack. Keeping it at the provable minimum matters:
        # an oversized M weakens the LP relaxation, which is the usual reason a MILP that is
        # merely large becomes a MILP that is slow.
        big_m = 2 * bound
        model.add(scaled_cross - raw_cross * scale - partner_doubled * big_m, hi=0)
        model.add(scaled_cross - raw_cross * scale + partner_doubled * big_m, lo=0)
        model.add(scaled_cross - raw_cross + (partner_doubled - 1) * big_m, hi=0)
        model.add(scaled_cross - raw_cross - (partner_doubled - 1) * big_m, lo=0)
        score[dancer.id] = best_fulfilled + scaled_cross + raw_same * scale
    return score, bound


def _build_best(model: Model, positive: list[tuple[int, Expr]], scale: int) -> Expr:
    """``max`` over the fulfilled wishes, as a column plus a selector.

    ``best >= c_i v_i`` alone would let the solver inflate it, and ``best <= sum`` would let a
    dancer double-collect. The selector -- exactly one operand chosen, and ``best`` bounded
    above by that operand -- is what makes it an exact maximum in both directions, which the
    pinned stages and the enumeration replay both rely on.
    """
    top = max(w for w, _ in positive) * scale
    best = Expr.of(model.integer(0, top))
    chosen: list[Expr] = []
    for weight, variable in positive:
        operand = variable * (weight * scale)
        selector = Expr.of(model.binary())
        chosen.append(selector)
        model.add(best - operand, lo=0)
        model.add(best - operand - (1 - selector) * top, hi=0)
    model.equal(Expr.sum(chosen), 1)
    return best


def _partner_doubled(
    model: Model,
    x: dict[tuple[str, int], int],
    doubled: dict[tuple[Role, int], int],
    team: Team,
    dancer_id: str,
) -> Expr:
    """True iff the dancer's position holds two dancers of the *opposite* role.

    That, not the dancer's own role count, is what doubles their number of cross-role partners.
    """
    opposite = team.dancers_by_id[dancer_id].role.opposite
    per_position: list[Expr] = []
    for p in team.positions:
        here = Expr.of(model.binary())
        occupied = Expr.of(x[(dancer_id, p)])
        opposite_doubled = Expr.of(doubled[(opposite, p)])
        model.add(here - occupied, hi=0)
        model.add(here - opposite_doubled, hi=0)
        model.add(here - occupied - opposite_doubled, lo=-1)
        per_position.append(here)
    # The dancer sits on exactly one position, so at most one term can be 1.
    return Expr.sum(per_position)


def _build_mismatch(
    model: Model, doubled: dict[tuple[Role, int], int], team: Team
) -> dict[int, int]:
    """One flag per position, true iff exactly one role is doubled there -- an exact XOR.

    See ``cpsat._build_mismatch`` for why minimising these can only ever be a tie-break.
    """
    mismatch: dict[int, int] = {}
    for p in team.positions:
        lead = Expr.of(doubled[(Role.LEADER, p)])
        follow = Expr.of(doubled[(Role.FOLLOWER, p)])
        flag = model.binary()
        expr = Expr.of(flag)
        model.add(expr - lead + follow, lo=0)
        model.add(expr - follow + lead, lo=0)
        model.add(expr - lead - follow, hi=0)
        model.add(expr + lead + follow, hi=2)
        mismatch[p] = flag
    return mismatch


# -- the stage sources --------------------------------------------------------------------


def _stage_source(model: Model, team: Team, config: SolverConfig, variables: _Vars) -> StageSource:
    """Yield the stages for ``config.objective``, then the soft coupled-position tie-break."""
    if config.objective is Objective.WEIGHTED_SUM:
        yield from _weighted_sum_stages(team, variables)
    elif config.objective is Objective.MAXIMIN_THEN_SUM:
        yield from _maximin_then_sum_stages(model, team, variables)
    elif config.objective is Objective.LEXIMIN:
        yield from _leximin_stages(model, team, variables)
    else:
        yield from _lexicographic_tier_stages(team, config, variables)

    if config.prefer_coupled and variables.mismatch:
        lopsided = Expr.sum([Expr.of(c) for c in variables.mismatch.values()])
        yield Stage("coupled", lopsided, Sense.MINIMIZE, tie_break=True)


def _total_score(team: Team, variables: _Vars) -> Expr:
    return Expr.sum([variables.score[dancer.id] for dancer in team.dancers])


def _weighted_sum_stages(team: Team, variables: _Vars) -> StageSource:
    """Single stage. See ``cpsat._weighted_sum_stages``."""
    yield Stage("sum", _total_score(team, variables), Sense.MAXIMIZE)


def _maximin_then_sum_stages(model: Model, team: Team, variables: _Vars) -> StageSource:
    """Lift the worst-off dancer first, then maximise the total at that floor."""
    bound = variables.score_bound
    floor = Expr.of(model.integer(-bound, bound))
    for dancer in team.dancers:
        model.add(floor - variables.score[dancer.id], hi=0)
    yield Stage("maximin", floor, Sense.MAXIMIZE, surrogate=True)
    yield Stage("sum", _total_score(team, variables), Sense.MAXIMIZE)


def _leximin_stages(model: Model, team: Team, variables: _Vars) -> StageSource:
    """Iteratively fix the current smallest score and re-solve on the remainder.

    See ``cpsat._leximin_stages`` for what the two stages per round mean. The conditional
    ``floor <= score`` -- enforced only for dancers still in play -- becomes a big-M row, and
    the ``above`` indicator a two-sided one.
    """
    bound = variables.score_bound
    # Scores and floors both live in [-bound, bound], so no row here can need more slack than
    # 2 * bound + 1. Tighter is better: an oversized M weakens the LP relaxation and this is
    # the stage the search spends most of its time in.
    big_m = 2 * bound + 1
    active: dict[str, Expr] | None = None
    round_index = 0

    while True:
        round_index += 1
        floor = Expr.of(model.integer(-bound, bound))
        for dancer in team.dancers:
            slack = Expr() if active is None else (1 - active[dancer.id]) * big_m
            model.add(floor - variables.score[dancer.id] - slack, hi=0)
        level = yield Stage(f"leximin.{round_index}.floor", floor, Sense.MAXIMIZE, surrogate=True)

        still_in_play: dict[str, Expr] = {}
        for dancer in team.dancers:
            above = Expr.of(model.binary())
            score = variables.score[dancer.id]
            # above == 1  ->  score >= level + 1 ; above == 0  ->  score <= level
            model.add(score - (level + 1) + (1 - above) * big_m, lo=0)
            model.add(score - level - above * big_m, hi=0)
            if active is None:
                still_in_play[dancer.id] = above
                continue
            both = Expr.of(model.binary())
            model.add(both - active[dancer.id], hi=0)
            model.add(both - above, hi=0)
            model.add(both - active[dancer.id] - above, lo=-1)
            still_in_play[dancer.id] = both

        remaining = yield Stage(
            f"leximin.{round_index}.count",
            Expr.sum(list(still_in_play.values())),
            Sense.MAXIMIZE,
        )
        if remaining == 0:
            return
        active = still_in_play


def _lexicographic_tier_stages(team: Team, config: SolverConfig, variables: _Vars) -> StageSource:
    """Maximise fulfilled tier-1 wishes, pin that, then tier 2. See ``cpsat``'s twin."""
    by_rank = _tier_expressions(team, config, variables)
    for direction, sense in (("desired", Sense.MAXIMIZE), ("not_desired", Sense.MINIMIZE)):
        for rank in sorted(by_rank.get(direction, {})):
            yield Stage(
                f"{direction}.tier{rank}", by_rank[direction][rank], sense, slack=config.tier_slack
            )


def _tier_expressions(
    team: Team, config: SolverConfig, variables: _Vars
) -> dict[str, dict[int, Expr]]:
    """Per direction and rank, the count of in-scope entries whose pair shares a position."""
    collected: dict[str, dict[int, list[Expr]]] = {"desired": {}, "not_desired": {}}
    for entry in team.preference_entries(config.scope):
        variable = variables.together[frozenset((entry.source, entry.target))]
        collected[entry.direction].setdefault(entry.rank, []).append(variable)
    return {
        direction: {rank: Expr.sum(items) for rank, items in sorted(ranks.items())}
        for direction, ranks in collected.items()
    }


# -- enumeration --------------------------------------------------------------------------


_NO_GOOD_HEADROOM: Final = 4
"""Extra re-solves allowed beyond the cap, to absorb signature-duplicate assignments."""


def _enumerate(
    team: Team,
    config: SolverConfig,
    recorded: list[StageResult],
    *,
    break_symmetry: bool,
) -> tuple[list[Solution], bool, float, int]:
    """Collect the optima by re-solving with a no-good cut per assignment already seen.

    This is the one place the two backends differ in kind rather than in notation. CP-SAT walks
    every solution of the pinned model inside a single search; HiGHS has no solution pool, so
    each further assignment costs another solve. The cut forbids exactly the previous
    assignment -- ``sum_{x=1}(1 - x) + sum_{x=0} x >= 1`` over the placement columns -- which
    is sound because those columns determine the solution completely.
    """
    model = _new_model(config)
    variables = _build_model(model, team, config, break_symmetry=break_symmetry)
    _replay_stages(model, _stage_source(model, team, config, variables), recorded, config)

    # A constant objective: every remaining assignment is equally acceptable, and the stages
    # have already been replayed as constraints.
    objective = Expr()
    limit = config.max_solutions + 1
    seen: set[frozenset[frozenset[str]]] = set()
    found: list[Solution] = []
    wall_time = 0.0
    nodes = 0
    exhausted = False

    for _ in range(limit + _NO_GOOD_HEADROOM):
        ok = model.optimize(objective, maximize=False)
        wall_time += model.wall_time
        nodes += model.num_nodes
        if not ok:
            exhausted = True
            break
        groups = _groups(model, team, variables)
        solution = build_solution(team, config, groups)
        if solution.signature not in seen:
            seen.add(solution.signature)
            found.append(solution)
            if len(found) >= limit:
                break
        _forbid(model, variables, groups, team)

    ordered = sorted(found, key=lambda s: ranking_key(s, config))
    truncated = len(ordered) > config.max_solutions or not exhausted
    solutions = ordered[: config.max_solutions]
    logger.info("enumerated %d solution(s), truncated=%s", len(solutions), truncated)
    return solutions, truncated, wall_time, nodes


def _forbid(model: Model, variables: _Vars, groups: list[list[str]], team: Team) -> None:
    """Add a no-good cut ruling out exactly this assignment."""
    placed = {(dancer_id, p) for p, group in enumerate(groups) for dancer_id in group}
    expr = Expr()
    ones = 0
    for dancer in team.dancers:
        for p in team.positions:
            column = Expr.of(variables.x[(dancer.id, p)])
            if (dancer.id, p) in placed:
                expr = expr - column
                ones += 1
            else:
                expr = expr + column
    model.add(expr, lo=1 - ones)


def _replay_stages(
    model: Model, source: StageSource, recorded: list[StageResult], config: SolverConfig
) -> None:
    """Rebuild pass 1's stages on a fresh model and pin each to its recorded optimum."""
    history: list[_Stage] = []
    try:
        stage = next(source)
    except StopIteration:  # pragma: no cover -- every objective yields at least one stage
        return
    for result in recorded:
        if stage.name != result.name:  # pragma: no cover -- the generator is deterministic
            raise AssertionError(f"stage replay diverged: {stage.name!r} != {result.name!r}")
        if stage.tie_break:
            _replay_lock_in(model, history, recorded)
        _pin(model, stage, result.value, _slack_for(result.value, config.near_optimal_ratio))
        history.append(stage)
        try:
            stage = source.send(result.value)
        except StopIteration:
            break
    _replay_lock_in(model, history, recorded)


def _replay_lock_in(model: Model, history: list[_Stage], recorded: list[StageResult]) -> None:
    """Reproduce ``_lock_in``'s guard from the recorded floors."""
    by_name = {result.name: result for result in recorded}
    for stage in history:
        if stage.slack == 0:
            continue
        locked = by_name[stage.name].locked_at
        if locked is None:  # pragma: no cover -- a slack stage is always locked in pass 1
            continue
        if stage.sense is Sense.MAXIMIZE:
            model.add(stage.expr, lo=locked)
        else:
            model.add(stage.expr, hi=locked)
