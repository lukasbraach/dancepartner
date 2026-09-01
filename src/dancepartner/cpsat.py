"""The CP-SAT backend: model construction, staged optimisation, solution enumeration.

The model is built once per pass; the objective is optimised in stages, each stage pinning its
achieved optimum before the next one runs. That is what keeps ``MAXIMIN_THEN_SUM`` honest:
stage 2 may not buy total score by lowering the worst-off dancer.

Stages come from a **generator** rather than a list, because ``LEXIMIN`` cannot know its later
stages until it sees the earlier optima. The generator yields a :class:`Stage` and receives the
achieved value back via ``send``, which makes it deterministic given that sequence of values --
and that is what lets the enumeration pass rebuild exactly the same stages on a fresh model.

Enumeration is a second pass: a fresh model, every stage pinned (optionally with slack) as a
*constraint* instead of an objective, and ``enumerate_all_solutions`` on. See
:func:`_enumerate`.

This module is the only one that imports ortools, and it is excluded from the browser bundle,
which has no WebAssembly wheel for it (SPEC.md 14.2). Reach it through
:func:`dancepartner.solver.solve`, never directly.
"""

from __future__ import annotations

import logging
from collections.abc import Generator
from dataclasses import dataclass, field

from ortools.sat.python import cp_model

from .feasibility import check_feasibility, veto_pairs
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

NAME = "cpsat"
"""Backend identifier, as recorded on :attr:`dancepartner.results.SolveResult.backend`."""

_CpStage = Stage[cp_model.LinearExpr]
"""One objective stage over CP-SAT expressions."""

StageSource = Generator[_CpStage, int, None]
"""Yields stages, receives each achieved optimum. See the module docstring."""


@dataclass
class _Vars:
    """The CP-SAT variables of one built model."""

    x: dict[tuple[str, int], cp_model.IntVar]
    together: dict[frozenset[str], cp_model.IntVar]
    role_count: dict[tuple[Role, int], cp_model.IntVar]
    doubled: dict[tuple[Role, int], cp_model.IntVar]
    score: dict[str, cp_model.IntVar]
    mismatch: dict[int, cp_model.IntVar] = field(default_factory=dict)
    score_bound: int = 0


# -- entry point --------------------------------------------------------------------------


def solve(
    team: Team,
    config: SolverConfig | None = None,
    *,
    skip_precheck: bool = False,
    break_symmetry: bool = True,
) -> SolveResult:
    """Solve the assignment problem and return a shortlist of optima.

    Args:
        team: The instance.
        config: Solver configuration; defaults to ``SolverConfig()``.
        skip_precheck: Skip ``feasibility.check_feasibility``. Only for tests that want to see
            how CP-SAT reacts to an instance the counting checks already reject.
        break_symmetry: Add the canonical position numbering. Off only for the test that
            asserts symmetry breaking does not change the optimum.

    Raises:
        InfeasibleInstanceError: The counting pre-checks found an obstruction.
    """
    config = config or SolverConfig()
    if not skip_precheck:
        issues = check_feasibility(team, config)
        if issues:
            raise InfeasibleInstanceError(issues)

    # Pass 1: find the stage optima.
    model = cp_model.CpModel()
    variables = _build_model(model, team, config, break_symmetry=break_symmetry)
    solver = _make_solver(config)
    stages, status, wall_time, num_branches = _run_stages(
        model, solver, _stage_source(model, team, config, variables)
    )

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return SolveResult(
            backend=NAME,
            status=solver.status_name(status),
            solutions=[],
            stages=stages,
            wall_time=wall_time,
            num_branches=num_branches,
        )

    if config.max_solutions == 1:
        groups = _extract_groups(solver, team, variables)
        return SolveResult(
            backend=NAME,
            status=solver.status_name(status),
            solutions=[build_solution(team, config, groups)],
            stages=stages,
            wall_time=wall_time,
            num_branches=num_branches,
        )

    # Pass 2: enumerate the ties on a fresh model with the same stages pinned.
    solutions, truncated, extra_time, extra_branches = _enumerate(
        team, config, stages, break_symmetry=break_symmetry
    )
    return SolveResult(
        backend=NAME,
        status=solver.status_name(status),
        solutions=solutions,
        stages=stages,
        truncated=truncated,
        wall_time=wall_time + extra_time,
        num_branches=num_branches + extra_branches,
    )


def _make_solver(config: SolverConfig) -> cp_model.CpSolver:
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = config.max_time_in_seconds
    solver.parameters.random_seed = config.random_seed
    solver.parameters.num_workers = config.num_workers
    solver.parameters.log_search_progress = config.log_search_progress
    return solver


# -- running the stages -------------------------------------------------------------------


def _run_stages(
    model: cp_model.CpModel, solver: cp_model.CpSolver, source: StageSource
) -> tuple[list[StageResult], cp_model.CpSolverStatus, float, int]:
    """Optimise each stage in turn, pinning its optimum before the next one is built.

    The pin is an inequality rather than an equality (``expr >= optimum - slack`` when
    maximising). With zero slack that is exactly equivalent -- constraints only ever shrink the
    feasible set, so the optimum can never be beaten later -- and with slack it is what SPEC.md
    8's epsilon means.
    """
    results: list[StageResult] = []
    history: list[_CpStage] = []
    status = cp_model.UNKNOWN
    # A CpSolver reports only its most recent solve, and there is one solve per stage. These
    # have to be accumulated here or the reported figures silently become "the last stage"
    # rather than the whole search -- which, on a staged objective, is most of it.
    wall_time = 0.0
    num_branches = 0
    try:
        stage = next(source)
    except StopIteration:  # pragma: no cover -- every objective yields at least one stage
        return results, status, wall_time, num_branches

    while True:
        if stage.tie_break:
            results = _lock_in(model, solver, history, results)
        if stage.sense is Sense.MAXIMIZE:
            model.maximize(stage.expr)
        else:
            model.minimize(stage.expr)
        status = solver.solve(model)
        wall_time += solver.wall_time
        num_branches += solver.num_branches
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            logger.warning("stage %s ended with status %s", stage.name, solver.status_name(status))
            source.close()
            return results, status, wall_time, num_branches

        value = round(solver.objective_value)
        logger.info("stage %s (%s) = %d", stage.name, stage.sense.value, value)
        results.append(StageResult(name=stage.name, sense=stage.sense, value=value))
        _pin(model, stage, value, extra_slack=0)
        history.append(stage)
        try:
            stage = source.send(value)
        except StopIteration:
            break
    # The sequence is over, so nothing is entitled to spend the remaining slack any more --
    # least of all the enumeration pass, which would otherwise offer the coach a shortlist of
    # assignments worse than the one the stages actually achieved.
    return _lock_in(model, solver, history, results), status, wall_time, num_branches


def _lock_in(
    model: cp_model.CpModel,
    solver: cp_model.CpSolver,
    history: list[_CpStage],
    results: list[StageResult],
) -> list[StageResult]:
    """Stop a tie-break stage from spending an earlier stage's slack.

    A stage pinned with slack (``SolverConfig.tier_slack``) is only meant to be traded against
    the *other* stages of its group -- tier 2 may buy from tier 1. Nothing else is entitled to
    that epsilon: not a tie-break like ``coupled``, which exists to pick between equally good
    assignments and so must leave "equally good" meaning what it says, and not the enumeration
    pass, which would otherwise put assignments on the shortlist that are strictly worse than
    the one the stages achieved.

    So this is called twice: before any tie-break stage, and once the stage sequence ends. Each
    slack-pinned stage is re-pinned at the value the current solution actually delivers. That
    solution stays feasible, so the extra constraint can never make the model infeasible; it
    just withdraws the licence to make anything worse. The achieved values are recorded on the
    ``StageResult`` as ``locked_at`` so the enumeration pass can reproduce the same guard.
    """
    locked = list(results)
    for index, stage in enumerate(history):
        if stage.slack == 0:
            continue
        achieved = round(solver.value(stage.expr))
        if stage.sense is Sense.MAXIMIZE:
            model.add(stage.expr >= achieved)
        else:
            model.add(stage.expr <= achieved)
        locked[index] = results[index].model_copy(update={"locked_at": achieved})
        logger.info("locked stage %s at %d", stage.name, achieved)
    return locked


def _pin(model: cp_model.CpModel, stage: _CpStage, value: int, extra_slack: int) -> None:
    """Constrain a stage's expression to its achieved optimum, within slack."""
    slack = stage.slack + extra_slack
    if stage.sense is Sense.MAXIMIZE:
        if stage.surrogate:
            # A maximin floor variable. Fixing it to the relaxed threshold both applies the
            # slack (via `floor <= score[d]`) and keeps the variable from floating.
            model.add(stage.expr == value - slack)
        else:
            model.add(stage.expr >= value - slack)
    else:
        model.add(stage.expr <= value + slack)


def _slack_for(value: int, ratio: float) -> int:
    """How far below a stage optimum the enumeration still accepts.

    Computed from ``abs(value)`` so that a ratio of 0.95 widens the admissible band for a
    negative optimum as well. Taking ``0.95 * value`` directly would *tighten* it there, which
    is the opposite of what "near-optimal" means.
    """
    if ratio >= 1.0:
        return 0
    return int((1.0 - ratio) * abs(value))


# -- model construction ------------------------------------------------------------------


def _build_model(
    model: cp_model.CpModel, team: Team, config: SolverConfig, *, break_symmetry: bool
) -> _Vars:
    x = {
        (dancer.id, p): model.new_bool_var(f"x[{dancer.id},{p}]")
        for dancer in team.dancers
        for p in team.positions
    }

    # 1. Every dancer occupies exactly one position.
    for dancer in team.dancers:
        model.add_exactly_one(x[(dancer.id, p)] for p in team.positions)

    # 2. Per position and per role: one or two dancers. Leader- and follower-doubling are
    #    independent; coupling them is a soft preference, see _stage_source.
    role_count: dict[tuple[Role, int], cp_model.IntVar] = {}
    for role in Role:
        members = team.by_role(role)
        for p in team.positions:
            count = model.new_int_var(1, 2, f"count[{role.value},{p}]")
            model.add(count == sum(x[(dancer.id, p)] for dancer in members))
            role_count[(role, p)] = count

    # 3./4. Pole position and coaching need, enforced on the position the dancer occupies.
    for dancer in team.dancers:
        for p in team.positions:
            own = role_count[(dancer.role, p)]
            if dancer.is_pole_position:
                model.add(own == 1).only_enforce_if(x[(dancer.id, p)])
            elif dancer.needs_coaching:
                model.add(own >= 2).only_enforce_if(x[(dancer.id, p)])

    # 5. At most one dancer with a coaching need per role per position. Together with 4.,
    #    every coaching dancer shares their position with an *experienced* same-role dancer.
    for role in Role:
        coaching = [dancer for dancer in team.by_role(role) if dancer.needs_coaching]
        if len(coaching) > 1:
            for p in team.positions:
                model.add_at_most_one(x[(dancer.id, p)] for dancer in coaching)

    together = {pair: _reify_together(model, x, team, pair) for pair in scored_pairs(team, config)}

    # 6. Hard vetoes.
    for pair in veto_pairs(team, config):
        model.add(together[pair] == 0)

    if break_symmetry:
        _break_symmetry(model, x, team)

    doubled = _build_doubled(model, role_count, team)
    score, score_bound = _build_scores(model, x, together, doubled, team, config)
    mismatch = _build_mismatch(model, doubled, team) if config.prefer_coupled else {}
    return _Vars(
        x=x,
        together=together,
        role_count=role_count,
        doubled=doubled,
        score=score,
        mismatch=mismatch,
        score_bound=score_bound,
    )


def _build_doubled(
    model: cp_model.CpModel, role_count: dict[tuple[Role, int], cp_model.IntVar], team: Team
) -> dict[tuple[Role, int], cp_model.IntVar]:
    """Reify "this position carries two dancers of this role", once per (role, position).

    The role counts are already constrained to ``{1, 2}``, so ``count == 2`` and ``count == 1``
    are exact complements and the reification needs no third case.
    """
    doubled: dict[tuple[Role, int], cp_model.IntVar] = {}
    for role in Role:
        for p in team.positions:
            flag = model.new_bool_var(f"doubled[{role.value},{p}]")
            model.add(role_count[(role, p)] == 2).only_enforce_if(flag)
            model.add(role_count[(role, p)] == 1).only_enforce_if(flag.negated())
            doubled[(role, p)] = flag
    return doubled


def _reify_together(
    model: cp_model.CpModel,
    x: dict[tuple[str, int], cp_model.IntVar],
    team: Team,
    pair: frozenset[str],
) -> cp_model.IntVar:
    """Reify "these two dancers share a position".

    Both implications are mandatory. With only the forward one, and negative weights in the
    objective, the solver would happily set the variable to 0 for a pair that does share a
    position and erase the dislike penalty. See
    ``tests/test_solver.py::test_reification_cannot_erase_dislike``.
    """
    d, e = sorted(pair)
    per_position: list[cp_model.IntVar] = []
    for p in team.positions:
        b = model.new_bool_var(f"together[{d},{e},{p}]")
        model.add_bool_and([x[(d, p)], x[(e, p)]]).only_enforce_if(b)
        model.add_bool_or([x[(d, p)].negated(), x[(e, p)].negated()]).only_enforce_if(b.negated())
        per_position.append(b)
    # Each dancer sits on exactly one position, so at most one b can be true; the sum is a
    # boolean and needs no further reification.
    total = model.new_bool_var(f"together[{d},{e}]")
    model.add(total == sum(per_position))
    return total


def _break_symmetry(
    model: cp_model.CpModel, x: dict[tuple[str, int], cp_model.IntVar], team: Team
) -> None:
    """Canonical position numbering over the leaders, in input order.

    Positions are unordered, so without this the search space carries a factor of
    ``n_positions!`` (40320 for eight). Leader *i* may only open position *p* if some leader
    *j < i* already occupies position *p - 1*, which forces positions to be filled in order.
    """
    leaders = team.by_role(Role.LEADER)
    for i, leader in enumerate(leaders):
        for p in team.positions:
            if p == 0:
                continue
            earlier = [x[(other.id, p - 1)] for other in leaders[:i]]
            if earlier:
                model.add(x[(leader.id, p)] <= sum(earlier))
            else:
                model.add(x[(leader.id, p)] == 0)


def _build_scores(
    model: cp_model.CpModel,
    x: dict[tuple[str, int], cp_model.IntVar],
    together: dict[frozenset[str], cp_model.IntVar],
    doubled: dict[tuple[Role, int], cp_model.IntVar],
    team: Team,
    config: SolverConfig,
) -> tuple[dict[str, cp_model.IntVar], int]:
    """One integer score variable per dancer, on ``config.score_scale``.

    ``score[d] = sum_e weight(d, e) * together[d, e]``, with the cross-role part halved when
    the dancer's position holds two dancers of the opposite role. Under
    ``ScoreAggregation.BEST`` the positive weights leave that sum and enter as
    ``max_e weight(d, e) * scale * together[d, e]`` instead — never halved, because a maximum
    cannot double-collect (see ``SolverConfig.aggregation``); the negative weights keep the
    summed, halved semantics.

    Returns the score variables and the absolute bound their domain was given, which the
    maximin stage reuses for ``lo``.
    """
    weights = build_weights(team, config)
    by_id = team.dancers_by_id
    scale = config.score_scale

    cross_terms: dict[str, list[tuple[int, cp_model.IntVar]]] = {d.id: [] for d in team.dancers}
    same_terms: dict[str, list[tuple[int, cp_model.IntVar]]] = {d.id: [] for d in team.dancers}
    for (source, target), weight in weights.items():
        # Every weight scheme yields a magnitude of at least 1, so there is no zero case.
        variable = together[frozenset((source, target))]
        bucket = cross_terms if by_id[source].role is not by_id[target].role else same_terms
        bucket[source].append((weight, variable))

    bound = sum(abs(weight) for weight in weights.values()) * scale + 1
    score: dict[str, cp_model.IntVar] = {}
    for dancer in team.dancers:
        cross = cross_terms[dancer.id]
        same = same_terms[dancer.id]

        best_fulfilled: cp_model.IntVar | int = 0
        if config.aggregation is ScoreAggregation.BEST:
            positive = [(w, v) for w, v in (*cross, *same) if w > 0]
            cross = [(w, v) for w, v in cross if w < 0]
            same = [(w, v) for w, v in same if w < 0]
            if positive:
                top = max(w for w, _ in positive) * scale
                best = model.new_int_var(0, top, f"best[{dancer.id}]")
                # Every operand is 0 or w * scale, so the max is 0 when nothing is fulfilled.
                model.add_max_equality(best, [w * scale * v for w, v in positive])
                best_fulfilled = best

        raw_cross = sum(weight * variable for weight, variable in cross)
        raw_same = sum(weight * variable for weight, variable in same)

        if not config.normalize_double or not cross:
            total = model.new_int_var(-bound, bound, f"score[{dancer.id}]")
            model.add(total == best_fulfilled + scale * raw_cross + scale * raw_same)
            score[dancer.id] = total
            continue

        partner_doubled = _partner_doubled(model, x, doubled, team, dancer.id)
        scaled_cross = model.new_int_var(-bound, bound, f"scaled_cross[{dancer.id}]")
        # A binary factor, so two enforced linear equalities express the product exactly and
        # stay linear -- CP-SAT propagates that far better than AddMultiplicationEquality.
        model.add(scaled_cross == scale * raw_cross).only_enforce_if(partner_doubled.negated())
        model.add(scaled_cross == raw_cross).only_enforce_if(partner_doubled)
        total = model.new_int_var(-bound, bound, f"score[{dancer.id}]")
        model.add(total == best_fulfilled + scaled_cross + scale * raw_same)
        score[dancer.id] = total
    return score, bound


def _partner_doubled(
    model: cp_model.CpModel,
    x: dict[tuple[str, int], cp_model.IntVar],
    doubled: dict[tuple[Role, int], cp_model.IntVar],
    team: Team,
    dancer_id: str,
) -> cp_model.IntVar:
    """True iff the dancer's position holds two dancers of the *opposite* role.

    That, not the dancer's own role count, is what doubles their number of cross-role
    partners and therefore their score contributions.
    """
    opposite = team.dancers_by_id[dancer_id].role.opposite
    flag = model.new_bool_var(f"partner_doubled[{dancer_id}]")
    per_position: list[cp_model.IntVar] = []
    for p in team.positions:
        here = model.new_bool_var(f"partner_doubled[{dancer_id},{p}]")
        occupied = x[(dancer_id, p)]
        opposite_doubled = doubled[(opposite, p)]
        model.add_bool_and([occupied, opposite_doubled]).only_enforce_if(here)
        model.add_bool_or([occupied.negated(), opposite_doubled.negated()]).only_enforce_if(
            here.negated()
        )
        per_position.append(here)
    # The dancer sits on exactly one position, so at most one ``here`` can be true.
    model.add(flag == sum(per_position))
    return flag


def _build_mismatch(
    model: cp_model.CpModel, doubled: dict[tuple[Role, int], cp_model.IntVar], team: Team
) -> dict[int, cp_model.IntVar]:
    """True per position iff exactly one of the two roles is doubled there.

    Minimising the sum of these prefers real Doppelbesetzungen -- two full couples sharing a
    position -- over lopsided ones, which is why it can only ever be a tie-break: on an uneven
    roster ``abs(n_leaders - n_followers)`` positions are lopsided no matter what.

    That bound is a lower one, not a promise. Because this is the weakest stage, the earlier
    ones are already pinned when it runs, and normalisation actively pushes the other way: a
    dancer whose wish is granted scores more when their position holds a *single* dancer of the
    opposite role. On an instance with many granted wishes the achievable minimum is therefore
    often above ``abs(n_leaders - n_followers)``, and that is the correct trade -- wishes first.
    """
    mismatch: dict[int, cp_model.IntVar] = {}
    for p in team.positions:
        leader_doubled = doubled[(Role.LEADER, p)]
        follower_doubled = doubled[(Role.FOLLOWER, p)]
        flag = model.new_bool_var(f"mismatch[{p}]")
        model.add(flag == 1).only_enforce_if([leader_doubled, follower_doubled.negated()])
        model.add(flag == 1).only_enforce_if([leader_doubled.negated(), follower_doubled])
        model.add(flag == 0).only_enforce_if([leader_doubled, follower_doubled])
        model.add(flag == 0).only_enforce_if([leader_doubled.negated(), follower_doubled.negated()])
        mismatch[p] = flag
    return mismatch


# -- the stage sources --------------------------------------------------------------------


def _stage_source(
    model: cp_model.CpModel, team: Team, config: SolverConfig, variables: _Vars
) -> StageSource:
    """Yield the stages for ``config.objective``, then the soft coupled-position tie-break."""
    if config.objective is Objective.WEIGHTED_SUM:
        yield from _weighted_sum_stages(team, variables)
    elif config.objective is Objective.MAXIMIN_THEN_SUM:
        yield from _maximin_then_sum_stages(model, team, variables)
    elif config.objective is Objective.LEXIMIN:
        yield from _leximin_stages(model, team, variables)
    else:
        yield from _lexicographic_tier_stages(model, team, config, variables)

    if config.prefer_coupled and variables.mismatch:
        lopsided = cp_model.LinearExpr.sum(list(variables.mismatch.values()))
        yield Stage("coupled", lopsided, Sense.MINIMIZE, tie_break=True)


def _total_score(team: Team, variables: _Vars) -> cp_model.LinearExpr:
    return cp_model.LinearExpr.sum([variables.score[dancer.id] for dancer in team.dancers])


def _weighted_sum_stages(team: Team, variables: _Vars) -> StageSource:
    """Single stage. Reliably leaves one or two people with nothing; kept for comparison."""
    yield Stage("sum", _total_score(team, variables), Sense.MAXIMIZE)


def _maximin_then_sum_stages(model: cp_model.CpModel, team: Team, variables: _Vars) -> StageSource:
    """Lift the worst-off dancer first, then maximise the total at that floor."""
    bound = variables.score_bound
    floor = model.new_int_var(-bound, bound, "maximin_floor")
    for dancer in team.dancers:
        model.add(floor <= variables.score[dancer.id])
    yield Stage("maximin", floor, Sense.MAXIMIZE, surrogate=True)
    yield Stage("sum", _total_score(team, variables), Sense.MAXIMIZE)


def _leximin_stages(model: cp_model.CpModel, team: Team, variables: _Vars) -> StageSource:
    """Iteratively fix the current smallest score and re-solve on the remainder.

    Each round is two stages:

    1. ``leximin.<r>.floor`` -- maximise the smallest score among the dancers still *at or
       above* the previous round's floor.
    2. ``leximin.<r>.count`` -- maximise how many of them get strictly above that floor, which
       is the same as minimising how many are stuck at it.

    Round *r+1* then recurses on exactly those. The "who is still in play" indicators are
    reified from the scores, so the solver chooses *which* dancers escape the floor while the
    stage fixes only *how many* -- that freedom is what makes this a leximin rather than a
    maximin repeated on an arbitrary set.

    The stages together pin the whole sorted score vector, and therefore the total as well, so
    no separate ``sum`` stage is needed or wanted here.
    """
    bound = variables.score_bound
    active: dict[str, cp_model.IntVar] | None = None
    round_index = 0

    while True:
        round_index += 1
        floor = model.new_int_var(-bound, bound, f"leximin_floor_{round_index}")
        for dancer in team.dancers:
            constraint = model.add(floor <= variables.score[dancer.id])
            if active is not None:
                constraint.only_enforce_if(active[dancer.id])
        level = yield Stage(f"leximin.{round_index}.floor", floor, Sense.MAXIMIZE, surrogate=True)

        still_in_play: dict[str, cp_model.IntVar] = {}
        for dancer in team.dancers:
            above = model.new_bool_var(f"above_{round_index}[{dancer.id}]")
            score = variables.score[dancer.id]
            model.add(score >= level + 1).only_enforce_if(above)
            model.add(score <= level).only_enforce_if(above.negated())
            if active is None:
                still_in_play[dancer.id] = above
                continue
            both = model.new_bool_var(f"in_play_{round_index}[{dancer.id}]")
            model.add_bool_and([active[dancer.id], above]).only_enforce_if(both)
            model.add_bool_or([active[dancer.id].negated(), above.negated()]).only_enforce_if(
                both.negated()
            )
            still_in_play[dancer.id] = both

        remaining = yield Stage(
            f"leximin.{round_index}.count",
            cp_model.LinearExpr.sum(list(still_in_play.values())),
            Sense.MAXIMIZE,
        )
        if remaining == 0:
            # Everyone is pinned at some round's floor; the vector is fully determined.
            return
        active = still_in_play


def _lexicographic_tier_stages(
    model: cp_model.CpModel, team: Team, config: SolverConfig, variables: _Vars
) -> StageSource:
    """Maximise fulfilled tier-1 wishes, pin that, then tier 2, and so on.

    This objective counts fulfilled wishes instead of scoring them, so the tier weights never
    enter the objective -- they only shape the reported scores.

    After the wish tiers come the mirror-image stages for the dislikes, strongest tier first.
    SPEC.md 8 only specifies the wish half; without the second half every dislike weaker than
    ``veto_tier`` would be ignored outright under this objective, which is not a trade the
    coach ever asked for.
    """
    del model  # the tier expressions are sums over existing `together` variables
    by_rank = _tier_expressions(team, config, variables)
    for direction, sense in (("desired", Sense.MAXIMIZE), ("not_desired", Sense.MINIMIZE)):
        for rank in sorted(by_rank.get(direction, {})):
            yield Stage(
                f"{direction}.tier{rank}",
                by_rank[direction][rank],
                sense,
                slack=config.tier_slack,
            )


def _tier_expressions(
    team: Team, config: SolverConfig, variables: _Vars
) -> dict[str, dict[int, cp_model.LinearExpr]]:
    """Per direction and rank, the count of in-scope entries whose pair shares a position."""
    collected: dict[str, dict[int, list[cp_model.IntVar]]] = {"desired": {}, "not_desired": {}}
    for entry in team.preference_entries(config.scope):
        variable = variables.together[frozenset((entry.source, entry.target))]
        collected[entry.direction].setdefault(entry.rank, []).append(variable)
    return {
        direction: {rank: cp_model.LinearExpr.sum(items) for rank, items in sorted(ranks.items())}
        for direction, ranks in collected.items()
    }


# -- enumeration --------------------------------------------------------------------------


class _Collector(cp_model.CpSolverSolutionCallback):
    """Collects deduplicated assignments until the cap is reached."""

    def __init__(
        self,
        team: Team,
        config: SolverConfig,
        x: dict[tuple[str, int], cp_model.IntVar],
        limit: int,
    ) -> None:
        """Set up the collector for one enumeration pass."""
        super().__init__()
        self._team = team
        self._config = config
        self._x = x
        self._limit = limit
        self._seen: set[frozenset[frozenset[str]]] = set()
        self.solutions: list[Solution] = []

    def on_solution_callback(self) -> None:
        """Record one solution, and stop the search once the cap is reached."""
        groups = [
            [dancer.id for dancer in self._team.dancers if self.value(self._x[(dancer.id, p)])]
            for p in self._team.positions
        ]
        solution = build_solution(self._team, self._config, groups)
        # SPEC.md 8: the frozenset of frozensets of dancer ids per position is the honest key.
        # Symmetry breaking already makes the labelling canonical, so in practice this catches
        # nothing -- but it is the guard that makes the shortlist correct if it is ever off.
        if solution.signature in self._seen:
            return
        self._seen.add(solution.signature)
        self.solutions.append(solution)
        if len(self.solutions) >= self._limit:
            self.stop_search()


def _enumerate(
    team: Team,
    config: SolverConfig,
    recorded: list[StageResult],
    *,
    break_symmetry: bool,
) -> tuple[list[Solution], bool, float, int]:
    """Collect the optima on a fresh model with every stage pinned instead of optimised.

    Preference problems have many equal optima, and the coach needs to see a handful of them
    rather than whichever one CP-SAT happened to prove first. The stage generator is replayed
    against the recorded values, which reproduces exactly the stages of pass 1 -- including
    ``LEXIMIN``'s, whose later rounds depend on the earlier optima.
    """
    model = cp_model.CpModel()
    variables = _build_model(model, team, config, break_symmetry=break_symmetry)
    _replay_stages(model, _stage_source(model, team, config, variables), recorded, config)

    solver = _make_solver(config)
    # Full enumeration is only well defined on a single worker.
    solver.parameters.num_workers = 1
    solver.parameters.enumerate_all_solutions = True
    # Collect one more than asked for: that extra solution is the only honest way to tell
    # "there are exactly N" from "we stopped counting at N".
    collector = _Collector(team, config, variables.x, config.max_solutions + 1)
    status = solver.solve(model, collector)

    found = sorted(collector.solutions, key=lambda s: ranking_key(s, config))
    truncated = len(found) > config.max_solutions or status == cp_model.UNKNOWN
    solutions = found[: config.max_solutions]
    logger.info(
        "enumerated %d solution(s), truncated=%s, status %s",
        len(solutions),
        truncated,
        solver.status_name(status),
    )
    return solutions, truncated, solver.wall_time, solver.num_branches


def _replay_stages(
    model: cp_model.CpModel,
    source: StageSource,
    recorded: list[StageResult],
    config: SolverConfig,
) -> None:
    """Rebuild pass 1's stages on a fresh model and pin each to its recorded optimum.

    The generator is deterministic given the sequence of achieved values, which is what makes
    replay possible at all -- ``LEXIMIN``'s later rounds only exist because of the earlier
    optima. ``_lock_in``'s guard is reproduced from the recorded ``locked_at`` floors.
    """
    history: list[_CpStage] = []
    try:
        stage = next(source)
    except StopIteration:  # pragma: no cover -- every objective yields at least one stage
        return
    for result in recorded:
        if stage.name != result.name:  # pragma: no cover -- the generator is deterministic
            raise AssertionError(f"stage replay diverged: {stage.name!r} != {result.name!r}")
        if stage.tie_break:
            _replay_lock_in(model, history, recorded, config)
        _pin(model, stage, result.value, _slack_for(result.value, config.near_optimal_ratio))
        history.append(stage)
        try:
            stage = source.send(result.value)
        except StopIteration:
            break
    _replay_lock_in(model, history, recorded, config)


def _replay_lock_in(
    model: cp_model.CpModel,
    history: list[_CpStage],
    recorded: list[StageResult],
    config: SolverConfig,
) -> None:
    """Reapply ``_lock_in``'s guard on the enumeration model, from the recorded values.

    The enumeration keeps its ``near_optimal_ratio`` band around each locked-in floor -- that
    band is what the shortlist is *for*. What it must not reproduce is the tie-break's ability
    to spend an earlier stage's tier slack, which is what the guard removes.
    """
    by_name = {result.name: result for result in recorded}
    for stage in history:
        result = by_name.get(stage.name)
        if result is None or result.locked_at is None:  # pragma: no cover -- names always match
            continue
        slack = _slack_for(result.locked_at, config.near_optimal_ratio)
        if stage.sense is Sense.MAXIMIZE:
            model.add(stage.expr >= result.locked_at - slack)
        else:
            model.add(stage.expr <= result.locked_at + slack)


def _extract_groups(solver: cp_model.CpSolver, team: Team, variables: _Vars) -> list[list[str]]:
    """Read the dancer ids per position out of a solved model."""
    groups: list[list[str]] = []
    for p in team.positions:
        groups.append(
            [dancer.id for dancer in team.dancers if solver.value(variables.x[(dancer.id, p)])]
        )
    return groups
