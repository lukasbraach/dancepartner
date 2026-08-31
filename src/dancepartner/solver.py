"""CP-SAT model construction and staged optimisation.

The model is built once; the objective is optimised in stages, each stage pinning its
achieved optimum before the next one runs. That is what keeps ``MAXIMIN_THEN_SUM`` honest:
stage 2 may not buy total score by lowering the worst-off dancer.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

from ortools.sat.python import cp_model
from pydantic import BaseModel, ConfigDict

from .feasibility import FeasibilityIssue, check_feasibility, veto_pairs
from .model import Objective, Role, SolverConfig, Team
from .scoring import Solution, build_solution, build_weights, scored_pairs

__all__ = ["InfeasibleInstanceError", "Sense", "SolveResult", "solve"]

logger = logging.getLogger(__name__)


class Sense(Enum):
    """Optimisation direction of one objective stage."""

    MAXIMIZE = "maximize"
    MINIMIZE = "minimize"


class InfeasibleInstanceError(ValueError):
    """The counting pre-checks rejected the instance before the solver ran."""

    def __init__(self, issues: list[FeasibilityIssue]) -> None:
        """Store the issues and build a German-carrying English exception message."""
        self.issues = issues
        joined = "; ".join(f"[{issue.code}] {issue.message_de}" for issue in issues)
        super().__init__(f"instance is infeasible by counting: {joined}")


class StageResult(BaseModel):
    """The outcome of one objective stage."""

    model_config = ConfigDict(frozen=True)

    name: str
    sense: Sense
    value: int


class SolveResult(BaseModel):
    """Everything a solve produced.

    Attributes:
        status: CP-SAT status name of the final stage.
        solutions: Optimal (and, from Milestone 3, near-optimal) assignments. At most one
            entry until solution enumeration lands.
        stages: Per-stage objective values, in the order they were optimised.
        wall_time: Total solver wall time across all stages, in seconds.
        num_branches: Total branches explored across all stages.
    """

    model_config = ConfigDict(frozen=True)

    status: str
    solutions: list[Solution]
    stages: list[StageResult] = []
    wall_time: float = 0.0
    num_branches: int = 0

    @property
    def best(self) -> Solution:
        """The best solution found; raises if there is none."""
        if not self.solutions:
            raise ValueError(f"no solution found (status {self.status})")
        return self.solutions[0]


@dataclass
class _Vars:
    """The CP-SAT variables of one built model."""

    x: dict[tuple[str, int], cp_model.IntVar]
    together: dict[frozenset[str], cp_model.IntVar]
    role_count: dict[tuple[Role, int], cp_model.IntVar]
    doubled: dict[tuple[Role, int], cp_model.IntVar]
    score: dict[str, cp_model.IntVar]
    mismatch: dict[int, cp_model.IntVar]
    score_bound: int


def solve(
    team: Team,
    config: SolverConfig | None = None,
    *,
    skip_precheck: bool = False,
    break_symmetry: bool = True,
) -> SolveResult:
    """Solve the assignment problem.

    Args:
        team: The instance.
        config: Solver configuration; defaults to ``SolverConfig()``.
        skip_precheck: Skip ``feasibility.check_feasibility``. Only for tests that want to
            see how CP-SAT reacts to an instance the counting checks already reject.
        break_symmetry: Add the canonical position numbering. Off only for the test that
            asserts symmetry breaking does not change the optimum.

    Raises:
        InfeasibleInstanceError: The counting pre-checks found an obstruction.
        NotImplementedError: ``config.objective`` is not implemented yet (Milestone 3).
    """
    config = config or SolverConfig()
    if not skip_precheck:
        issues = check_feasibility(team, config)
        if issues:
            raise InfeasibleInstanceError(issues)

    if config.objective in (Objective.LEXIMIN, Objective.LEXICOGRAPHIC_TIERS):
        raise NotImplementedError(f"objective {config.objective.value!r} arrives in Milestone 3")

    model = cp_model.CpModel()
    variables = _build_model(model, team, config, break_symmetry=break_symmetry)
    stages = _stages(model, team, config, variables)

    solver = _make_solver(config)
    stage_results: list[StageResult] = []
    wall_time = 0.0
    num_branches = 0
    status = cp_model.UNKNOWN

    for name, expression, sense in stages:
        if sense is Sense.MAXIMIZE:
            model.maximize(expression)
        else:
            model.minimize(expression)
        status = solver.solve(model)
        wall_time += solver.wall_time
        num_branches += solver.num_branches
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            logger.warning("stage %s ended with status %s", name, solver.status_name(status))
            return SolveResult(
                status=solver.status_name(status),
                solutions=[],
                stages=stage_results,
                wall_time=wall_time,
                num_branches=num_branches,
            )
        value = round(solver.objective_value)
        logger.info("stage %s (%s) = %d", name, sense.value, value)
        stage_results.append(StageResult(name=name, sense=sense, value=value))
        # Pin this stage's optimum so later stages can only break ties.
        model.add(expression == value)

    groups = _extract_groups(solver, team, variables)
    solution = build_solution(team, config, groups)
    return SolveResult(
        status=solver.status_name(status),
        solutions=[solution],
        stages=stage_results,
        wall_time=wall_time,
        num_branches=num_branches,
    )


def _make_solver(config: SolverConfig) -> cp_model.CpSolver:
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = config.max_time_in_seconds
    solver.parameters.random_seed = config.random_seed
    solver.parameters.num_workers = config.num_workers
    solver.parameters.log_search_progress = config.log_search_progress
    return solver


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

    # 2. Per position and per role: one or two dancers. Herren- and Damen-doubling are
    #    independent; coupling them is a soft preference, see _stages.
    role_count: dict[tuple[Role, int], cp_model.IntVar] = {}
    for role in Role:
        members = team.by_role(role)
        for p in team.positions:
            count = model.new_int_var(1, 2, f"count[{role.value},{p}]")
            model.add(count == sum(x[(dancer.id, p)] for dancer in members))
            role_count[(role, p)] = count

    # 3./4. Startanspruch and Coachingbedarf, enforced on the position the dancer occupies.
    for dancer in team.dancers:
        for p in team.positions:
            own = role_count[(dancer.role, p)]
            if dancer.has_startanspruch:
                model.add(own == 1).only_enforce_if(x[(dancer.id, p)])
            elif dancer.needs_coaching:
                model.add(own >= 2).only_enforce_if(x[(dancer.id, p)])

    together = {pair: _reify_together(model, x, team, pair) for pair in scored_pairs(team, config)}

    # 5. Hard vetoes.
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
    """Canonical position numbering over the Herren, in input order.

    Positions are unordered, so without this the search space carries a factor of
    ``n_positions!`` (40320 for eight). Herr *i* may only open position *p* if some Herr
    *j < i* already occupies position *p - 1*, which forces positions to be filled in order.
    """
    herren = team.by_role(Role.HERR)
    for i, herr in enumerate(herren):
        for p in team.positions:
            if p == 0:
                continue
            earlier = [x[(other.id, p - 1)] for other in herren[:i]]
            if earlier:
                model.add(x[(herr.id, p)] <= sum(earlier))
            else:
                model.add(x[(herr.id, p)] == 0)


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
    the dancer's position holds two dancers of the opposite role.

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
        raw_cross = sum(weight * variable for weight, variable in cross_terms[dancer.id])
        raw_same = sum(weight * variable for weight, variable in same_terms[dancer.id])

        if not config.normalize_double or not cross_terms[dancer.id]:
            total = model.new_int_var(-bound, bound, f"score[{dancer.id}]")
            model.add(total == scale * raw_cross + scale * raw_same)
            score[dancer.id] = total
            continue

        partner_doubled = _partner_doubled(model, x, doubled, team, dancer.id)
        scaled_cross = model.new_int_var(-bound, bound, f"scaled_cross[{dancer.id}]")
        # A binary factor, so two enforced linear equalities express the product exactly and
        # stay linear -- CP-SAT propagates that far better than AddMultiplicationEquality.
        model.add(scaled_cross == scale * raw_cross).only_enforce_if(partner_doubled.negated())
        model.add(scaled_cross == raw_cross).only_enforce_if(partner_doubled)
        total = model.new_int_var(-bound, bound, f"score[{dancer.id}]")
        model.add(total == scaled_cross + scale * raw_same)
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
    roster ``abs(n_herren - n_damen)`` positions are lopsided no matter what.

    That bound is a lower one, not a promise. Because this is the weakest stage, the earlier
    ones are already pinned when it runs, and normalisation actively pushes the other way: a
    dancer whose wish is granted scores more when their position holds a *single* dancer of the
    opposite role. On an instance with many granted wishes the achievable minimum is therefore
    often above ``abs(n_herren - n_damen)``, and that is the correct trade -- wishes first.
    """
    mismatch: dict[int, cp_model.IntVar] = {}
    for p in team.positions:
        herr_doubled = doubled[(Role.HERR, p)]
        dame_doubled = doubled[(Role.DAME, p)]
        flag = model.new_bool_var(f"mismatch[{p}]")
        model.add(flag == 1).only_enforce_if([herr_doubled, dame_doubled.negated()])
        model.add(flag == 1).only_enforce_if([herr_doubled.negated(), dame_doubled])
        model.add(flag == 0).only_enforce_if([herr_doubled, dame_doubled])
        model.add(flag == 0).only_enforce_if([herr_doubled.negated(), dame_doubled.negated()])
        mismatch[p] = flag
    return mismatch


# -- objective staging -------------------------------------------------------------------


def _stages(
    model: cp_model.CpModel, team: Team, config: SolverConfig, variables: _Vars
) -> list[tuple[str, cp_model.LinearExpr, Sense]]:
    """Build the ordered list of objective stages for ``config.objective``."""
    total = cp_model.LinearExpr.sum([variables.score[dancer.id] for dancer in team.dancers])
    stages: list[tuple[str, cp_model.LinearExpr, Sense]] = []

    if config.objective is Objective.MAXIMIN_THEN_SUM:
        bound = variables.score_bound
        lo = model.new_int_var(-bound, bound, "lo")
        for dancer in team.dancers:
            model.add(lo <= variables.score[dancer.id])
        stages.append(("maximin", lo, Sense.MAXIMIZE))

    stages.append(("sum", total, Sense.MAXIMIZE))

    if config.prefer_coupled and variables.mismatch:
        lopsided = cp_model.LinearExpr.sum(list(variables.mismatch.values()))
        stages.append(("coupled", lopsided, Sense.MINIMIZE))
    return stages


def _extract_groups(solver: cp_model.CpSolver, team: Team, variables: _Vars) -> list[list[str]]:
    """Read the dancer ids per position out of a solved model."""
    groups: list[list[str]] = []
    for p in team.positions:
        groups.append(
            [dancer.id for dancer in team.dancers if solver.value(variables.x[(dancer.id, p)])]
        )
    return groups
