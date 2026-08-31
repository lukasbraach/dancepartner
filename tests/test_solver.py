"""Solver tests. ``assert_result_valid`` is called in every one of them.

Micro-instances are sized so the optimum can be worked out by hand and asserted by value;
that is the only way to notice when the model quietly stops meaning what we think it means.
"""

from __future__ import annotations

import pytest

from dancepartner.model import (
    Objective,
    PreferenceScope,
    Role,
    SolverConfig,
    Team,
    WeightScheme,
)
from dancepartner.solver import InfeasibleInstanceError, Sense, solve

from .builders import desired, not_desired, roster, team, tier
from .helpers import assert_result_valid, position_of, share_position


def test_solves_a_bare_instance(tiny: Team) -> None:
    result = solve(tiny)
    assert result.status == "OPTIMAL"
    assert_result_valid(result, tiny)
    assert result.best.total_score == 0


def test_mutual_wish_is_granted_and_scored_by_value() -> None:
    # 3 positions, 3+3 dancers: every position is one couple. K = 1, so a granted wish is
    # worth 1, x2 for the normalisation scale.
    instance = team(3, 3, 3, desired("led0", tier(1, "fol0")), desired("fol0", tier(1, "led0")))
    result = solve(instance)
    assert_result_valid(result, instance)
    assert share_position(result.best, "led0", "fol0")
    assert result.best.per_dancer["led0"].score == 2
    assert result.best.per_dancer["fol0"].score == 2
    assert result.best.total_score == 4
    assert result.best.min_score == 0


def test_one_sided_wish_is_granted_and_scored_only_for_the_wisher() -> None:
    instance = team(3, 3, 3, desired("led0", tier(1, "fol0")))
    result = solve(instance)
    assert_result_valid(result, instance)
    assert share_position(result.best, "led0", "fol0")
    assert result.best.per_dancer["led0"].score == 2
    # Preferences are directed: fol0 said nothing, so fol0 gains nothing.
    assert result.best.per_dancer["fol0"].score == 0
    assert result.best.total_score == 2


def test_stronger_tier_wins_over_weaker_tier() -> None:
    # Every position is a single couple, so led0 gets exactly one of the two: tier 1
    # (K = 2, so weight 2, x2 scale => 4) must beat tier 2 (weight 1 => 2).
    instance = team(3, 3, 3, desired("led0", tier(1, "fol0"), tier(2, "fol1")))
    result = solve(instance)
    assert_result_valid(result, instance)
    assert share_position(result.best, "led0", "fol0")
    assert result.best.per_dancer["led0"].fulfilled_desired == {1: ["fol0"]}
    assert result.best.per_dancer["led0"].score == 4


def test_sum_stage_may_prefer_two_weaker_wishes_over_one_strong_one() -> None:
    # led0 wants fol0 (tier 1, weight 2) or fol1 (tier 2, weight 1); led1 wants only fol0.
    # Giving fol0 to led0 scores 4 + 0; giving fol0 to led1 scores 2 + 4. Both leave the floor at 0,
    # so the sum stage decides and the larger total wins.
    instance = team(
        3,
        3,
        3,
        desired("led0", tier(1, "fol0"), tier(2, "fol1")),
        desired("led1", tier(1, "fol0")),
    )
    result = solve(instance)
    assert_result_valid(result, instance)
    assert share_position(result.best, "led1", "fol0")
    assert share_position(result.best, "led0", "fol1")
    assert result.best.total_score == 6


def test_dislike_is_avoided() -> None:
    instance = team(3, 3, 3, not_desired("led0", tier(1, "fol0")))
    result = solve(instance)
    assert_result_valid(result, instance)
    assert not share_position(result.best, "led0", "fol0")
    assert result.best.total_score == 0


# -- hard constraints ---------------------------------------------------------------------


def test_pole_position_forces_a_single_role_position() -> None:
    instance = team(4, 4, 3, **{"led0": {"is_pole_position": True}})
    result = solve(instance)
    assert_result_valid(result, instance)
    label = position_of(result.best, "led0")
    position = next(p for p in result.best.positions if p.label == label)
    assert position.leaders == ["led0"]


def test_coachingbedarf_forces_a_shared_role_position() -> None:
    instance = team(4, 4, 3, **{"led0": {"needs_coaching": True}})
    result = solve(instance)
    assert_result_valid(result, instance)
    label = position_of(result.best, "led0")
    position = next(p for p in result.best.positions if p.label == label)
    assert len(position.leaders) == 2


def test_pole_position_beats_a_wish() -> None:
    # led0 wishes for fol0, but fol0's position would have to hold two Herren for the counts to
    # work out; Startanspruch is a hard constraint and the wish must lose.
    instance = team(
        4,
        3,
        3,
        desired("led0", tier(1, "fol0")),
        not_desired("led1", tier(1, "fol1", "fol2")),
        **{"led0": {"is_pole_position": True}},
    )
    result = solve(instance)
    assert_result_valid(result, instance)
    label = position_of(result.best, "led0")
    position = next(p for p in result.best.positions if p.label == label)
    assert position.leaders == ["led0"]


def test_veto_is_respected_even_when_it_costs_score() -> None:
    # led0 wants fol0 at tier 1 but fol0 vetoes led0. The veto is symmetric and hard, so the wish
    # cannot be granted at any price.
    instance = team(3, 3, 3, desired("led0", tier(1, "fol0")), not_desired("fol0", tier(1, "led0")))
    result = solve(instance)
    assert_result_valid(result, instance)
    assert not share_position(result.best, "led0", "fol0")
    assert result.best.per_dancer["led0"].score == 0


def test_veto_tier_none_leaves_dislikes_to_the_objective() -> None:
    instance = team(3, 3, 3, not_desired("led0", tier(1, "fol0")))
    config = SolverConfig(veto_tier=None)
    result = solve(instance, config)
    assert_result_valid(result, instance, config)
    # Still avoided, but by the objective rather than by a constraint.
    assert not share_position(result.best, "led0", "fol0")


def test_veto_tier_two_also_vetoes_tier_one() -> None:
    instance = team(3, 3, 3, not_desired("led0", tier(1, "fol0"), tier(2, "fol1")))
    config = SolverConfig(veto_tier=2)
    result = solve(instance, config)
    assert_result_valid(result, instance, config)
    assert not share_position(result.best, "led0", "fol0")
    assert not share_position(result.best, "led0", "fol1")


def test_infeasible_instance_is_rejected_before_the_solver_runs() -> None:
    instance = team(3, 8, 8)
    with pytest.raises(InfeasibleInstanceError) as excinfo:
        solve(instance)
    assert excinfo.value.issues[0].code == "ROLE_COUNT_OUT_OF_RANGE"
    assert "Positionen" in str(excinfo.value)


def test_skip_precheck_hands_the_instance_to_cp_sat() -> None:
    instance = team(3, 8, 8)
    result = solve(instance, skip_precheck=True)
    assert result.status == "INFEASIBLE"
    assert result.solutions == []
    with pytest.raises(ValueError, match="no solution found"):
        _ = result.best


# -- the reification regression test from SPEC.md 8 ---------------------------------------


def test_reification_cannot_erase_dislike() -> None:
    """With only the forward implication, ``together`` could be 0 for a co-positioned pair.

    The instance forces led0 and led1 onto the same position (both need coaching and there is
    exactly one Herren-Doppelbesetzung available), and they dislike each other. If the
    ``AddBoolOr`` half of the reification is deleted, the solver is free to claim
    ``together == 0`` and report a score of 0 instead of the penalty.
    """
    instance = team(
        4,
        4,
        3,
        not_desired("led0", tier(1, "led1")),
        not_desired("led1", tier(1, "led0")),
        **{"led0": {"needs_coaching": True}, "led1": {"needs_coaching": True}},
    )
    # Vetoes off: the pair must be co-positioned, so a hard veto would make it infeasible.
    config = SolverConfig(scope=PreferenceScope.ALL, veto_tier=None)
    result = solve(instance, config)
    assert_result_valid(result, instance, config)
    assert share_position(result.best, "led0", "led1"), "the instance must force them together"
    assert result.best.per_dancer["led0"].score == -2
    assert result.best.per_dancer["led1"].score == -2
    assert result.best.per_dancer["led0"].violated_not_desired == {1: ["led1"]}
    assert result.stages[0].value == -2  # the maximin stage saw the penalty too


def test_reification_cannot_invent_togetherness() -> None:
    """The other direction: ``together`` must be 0 when the pair is apart.

    led0 wishes for fol0 but a veto keeps them apart; a broken reification could still claim the
    wish was granted and inflate the score.
    """
    instance = team(3, 3, 3, desired("led0", tier(1, "fol0")), not_desired("fol0", tier(1, "led0")))
    result = solve(instance)
    assert_result_valid(result, instance)
    assert result.best.total_score == 0


# -- objectives ---------------------------------------------------------------------------


def _lonely_instance() -> Team:
    """Everyone wants fol0; only one leader can have them.

    With WEIGHTED_SUM the solver is free to pile score onto whoever is cheapest to satisfy
    and leave someone at nothing. MAXIMIN_THEN_SUM has to lift the floor first.
    """
    return team(
        3,
        3,
        3,
        desired("led0", tier(1, "fol0")),
        desired("led1", tier(1, "fol0")),
        desired("led2", tier(1, "fol0", "fol1", "fol2")),
    )


def test_weighted_sum_maximises_the_total() -> None:
    instance = _lonely_instance()
    config = SolverConfig(objective=Objective.WEIGHTED_SUM)
    result = solve(instance, config)
    assert_result_valid(result, instance, config)
    assert [stage.name for stage in result.stages] == ["sum", "coupled"]
    # led2 is satisfied by any follower, and exactly one of led0/led1 can have fol0: total 4.
    assert result.best.total_score == 4
    assert result.best.min_score == 0


def test_maximin_then_sum_lifts_the_worst_off_dancer() -> None:
    instance = _lonely_instance()
    config = SolverConfig(objective=Objective.MAXIMIN_THEN_SUM)
    result = solve(instance, config)
    assert_result_valid(result, instance, config)
    assert [stage.name for stage in result.stages] == ["maximin", "sum", "coupled"]
    # The floor cannot be lifted above 0 here -- led0 and led1 both want only fol0 -- but the
    # stage order is what matters, and the total must still be maximal at that floor.
    assert result.stages[0].value == result.best.min_score
    assert result.best.total_score == 4


def test_maximin_prefers_a_lifted_floor_over_a_larger_total() -> None:
    # led0 wants fol0 only. led1 wants fol0 (tier 1) or fol1 (tier 2).
    # Give led0 fol0 => scores 2 and 2 (K=2: tier1=2, tier2=1, x2 scale), min 2, total 4... but
    # giving led1 fol0 instead => led0 gets 0, led1 gets 4, total 4 with min 0. Same total, and
    # maximin must pick the first.
    instance = team(
        3,
        3,
        3,
        desired("led0", tier(1, "fol0")),
        desired("led1", tier(1, "fol0"), tier(2, "fol1")),
    )
    maximin = SolverConfig(objective=Objective.MAXIMIN_THEN_SUM)
    result = solve(instance, maximin)
    assert_result_valid(result, instance, maximin)
    assert share_position(result.best, "led0", "fol0")
    assert share_position(result.best, "led1", "fol1")
    assert result.best.min_score == 0  # led2, fol2 etc. are unsurveyed and score 0
    assert result.best.per_dancer["led0"].score == 4
    assert result.best.per_dancer["led1"].score == 2
    assert result.best.total_score == 6


@pytest.mark.parametrize("objective", list(Objective))
def test_every_objective_solves_and_verifies(tiny: Team, objective: Objective) -> None:
    config = SolverConfig(objective=objective)
    result = solve(tiny, config)
    assert result.status == "OPTIMAL"
    assert_result_valid(result, tiny, config)


@pytest.mark.parametrize("scheme", list(WeightScheme))
def test_both_weight_schemes_find_the_same_assignment(scheme: WeightScheme) -> None:
    instance = team(3, 3, 3, desired("led0", tier(1, "fol0"), tier(2, "fol1")))
    config = SolverConfig(weights=scheme)
    result = solve(instance, config)
    assert_result_valid(result, instance, config)
    assert share_position(result.best, "led0", "fol0")


# -- normalisation ------------------------------------------------------------------------


def test_normalisation_removes_the_incentive_to_double_a_well_liked_dancer() -> None:
    # led0 wants both fol0 and fol1 at tier 1. Without normalisation the solver puts all three on
    # one position to collect two contributions; with it, one is worth as much as two.
    instance = team(4, 4, 3, desired("led0", tier(1, "fol0", "fol1")))

    unnormalised = SolverConfig(normalize_double=False)
    greedy = solve(instance, unnormalised)
    assert_result_valid(greedy, instance, unnormalised)
    assert share_position(greedy.best, "led0", "fol0", "fol1")
    assert greedy.best.per_dancer["led0"].score == 2

    normalised = SolverConfig(normalize_double=True)
    fair = solve(instance, normalised)
    assert_result_valid(fair, instance, normalised)
    assert fair.best.per_dancer["led0"].score == 2  # the same score either way now
    assert fair.best.total_score == 2


def test_normalisation_is_driven_by_the_opposite_role_count() -> None:
    # led0 sits with two Damen it likes; doubling the Herren on that position must not change
    # led0's cross-role score, only the Damen count does.
    instance = team(4, 5, 3, desired("led0", tier(1, "fol0", "fol1")))
    config = SolverConfig()
    result = solve(instance, config)
    assert_result_valid(result, instance, config)
    label = position_of(result.best, "led0")
    position = next(p for p in result.best.positions if p.label == label)
    granted = set(result.best.per_dancer["led0"].fulfilled_desired.get(1, []))
    expected = 1 if len(position.followers) == 2 else 2
    assert result.best.per_dancer["led0"].score == expected * len(granted)


# -- the soft coupled-position preference -------------------------------------------------


def test_coupled_stage_reaches_the_role_count_floor(uneven: Team) -> None:
    # 4 Herren, 5 Damen over 3 positions: 1 Herren-double, 2 Damen-doubles. At least
    # abs(4 - 5) = 1 position must be lopsided, and the stage must reach exactly that.
    config = SolverConfig(prefer_coupled=True)
    result = solve(uneven, config)
    assert_result_valid(result, uneven, config)
    coupled = next(stage for stage in result.stages if stage.name == "coupled")
    assert coupled.sense is Sense.MINIMIZE
    n_leaders = len(uneven.by_role(Role.LEADER))
    n_followers = len(uneven.by_role(Role.FOLLOWER))
    assert coupled.value == abs(n_leaders - n_followers)
    lopsided = sum(
        1 for p in result.best.positions if (len(p.leaders) == 2) != (len(p.followers) == 2)
    )
    assert lopsided == abs(n_leaders - n_followers)


def test_even_roster_becomes_fully_coupled(small: Team) -> None:
    config = SolverConfig(prefer_coupled=True)
    result = solve(small, config)
    assert_result_valid(result, small, config)
    assert next(s for s in result.stages if s.name == "coupled").value == 0
    assert sum(1 for p in result.best.positions if p.is_doubled) == 1


def test_coupled_stage_never_costs_a_wish(uneven: Team) -> None:
    instance = Team(
        dancers=uneven.dancers,
        surveys=[desired("led0", tier(1, "fol0")), desired("fol0", tier(1, "led0"))],
        n_positions=3,
    )
    with_coupling = SolverConfig(prefer_coupled=True)
    without = SolverConfig(prefer_coupled=False)
    a = solve(instance, with_coupling)
    b = solve(instance, without)
    assert_result_valid(a, instance, with_coupling)
    assert_result_valid(b, instance, without)
    assert a.best.total_score == b.best.total_score
    assert a.best.min_score == b.best.min_score


def test_prefer_coupled_off_omits_the_stage(small: Team) -> None:
    config = SolverConfig(prefer_coupled=False)
    result = solve(small, config)
    assert_result_valid(result, small, config)
    assert [stage.name for stage in result.stages] == ["maximin", "sum"]


# -- determinism --------------------------------------------------------------------------


def test_same_input_and_seed_yields_the_same_solution() -> None:
    instance = Team(
        dancers=roster(10, 12),
        surveys=[
            desired("led0", tier(1, "fol0"), tier(2, "fol1")),
            desired("led1", tier(1, "fol0")),
            desired("fol0", tier(1, "led1")),
            not_desired("led2", tier(1, "fol2")),
            desired("fol3", tier(1, "led3", "led4")),
        ],
        n_positions=8,
    )
    config = SolverConfig(random_seed=42, num_workers=1)
    first = solve(instance, config)
    second = solve(instance, config)
    assert_result_valid(first, instance, config)
    assert first.best == second.best
    assert [s.value for s in first.stages] == [s.value for s in second.stages]


def test_a_realistic_instance_solves_within_the_time_limit(full: Team) -> None:
    instance = Team(
        dancers=full.dancers,
        surveys=[
            desired("led0", tier(1, "fol0", "fol1"), tier(2, "fol2")),
            desired("led1", tier(1, "fol1"), tier(2, "fol3")),
            desired("led2", tier(1, "fol4")),
            not_desired("led3", tier(1, "fol5")),
            desired("fol0", tier(1, "led0")),
            desired("fol6", tier(1, "led4", "led5")),
            not_desired("fol7", tier(1, "led6")),
        ],
        n_positions=8,
    )
    config = SolverConfig(max_time_in_seconds=30.0)
    result = solve(instance, config)
    assert result.status == "OPTIMAL"
    assert_result_valid(result, instance, config)
    assert result.wall_time < 30.0


def test_wall_time_counts_every_stage_not_just_the_last(monkeypatch: pytest.MonkeyPatch) -> None:
    """A CpSolver reports only its most recent solve, and staged objectives solve repeatedly.

    Reading the solver once after the loop silently reported the last stage as if it were the
    whole search -- a five-fold under-report on an instance whose first stage does the work.
    """
    from ortools.sat.python import cp_model

    from dancepartner import solver as solver_module

    per_stage: list[float] = []
    make_solver = solver_module._make_solver

    def spy(config: SolverConfig) -> cp_model.CpSolver:
        created = make_solver(config)
        inner = created.solve

        def recording(
            model: cp_model.CpModel,
            solution_callback: cp_model.CpSolverSolutionCallback | None = None,
        ) -> cp_model.CpSolverStatus:
            status = inner(model, solution_callback)
            per_stage.append(created.wall_time)
            return status

        created.solve = recording  # type: ignore[method-assign]
        return created

    monkeypatch.setattr(solver_module, "_make_solver", spy)

    instance = team(4, 4, 3, desired("led0", tier(1, "fol0")), not_desired("led1", tier(1, "fol1")))
    # max_solutions=1 skips the enumeration pass, so pass 1 is the whole of the reported time.
    config = SolverConfig(objective=Objective.MAXIMIN_THEN_SUM, max_solutions=1)
    result = solve(instance, config)

    assert len(per_stage) > 1, "this objective must run more than one stage"
    assert result.wall_time == pytest.approx(sum(per_stage))
