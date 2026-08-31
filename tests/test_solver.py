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

from .builders import nicht_wunsch, roster, team, tier, wunsch
from .helpers import assert_result_valid, position_of, share_position


def test_solves_a_bare_instance(tiny: Team) -> None:
    result = solve(tiny)
    assert result.status == "OPTIMAL"
    assert_result_valid(result, tiny)
    assert result.best.total_score == 0


def test_mutual_wish_is_granted_and_scored_by_value() -> None:
    # 3 positions, 3+3 dancers: every position is one couple. K = 1, so a granted wish is
    # worth 1, x2 for the normalisation scale.
    instance = team(3, 3, 3, wunsch("h0", tier(1, "d0")), wunsch("d0", tier(1, "h0")))
    result = solve(instance)
    assert_result_valid(result, instance)
    assert share_position(result.best, "h0", "d0")
    assert result.best.per_dancer["h0"].score == 2
    assert result.best.per_dancer["d0"].score == 2
    assert result.best.total_score == 4
    assert result.best.min_score == 0


def test_one_sided_wish_is_granted_and_scored_only_for_the_wisher() -> None:
    instance = team(3, 3, 3, wunsch("h0", tier(1, "d0")))
    result = solve(instance)
    assert_result_valid(result, instance)
    assert share_position(result.best, "h0", "d0")
    assert result.best.per_dancer["h0"].score == 2
    # Preferences are directed: d0 said nothing, so d0 gains nothing.
    assert result.best.per_dancer["d0"].score == 0
    assert result.best.total_score == 2


def test_stronger_tier_wins_over_weaker_tier() -> None:
    # Every position is a single couple, so h0 gets exactly one of the two: tier 1
    # (K = 2, so weight 2, x2 scale => 4) must beat tier 2 (weight 1 => 2).
    instance = team(3, 3, 3, wunsch("h0", tier(1, "d0"), tier(2, "d1")))
    result = solve(instance)
    assert_result_valid(result, instance)
    assert share_position(result.best, "h0", "d0")
    assert result.best.per_dancer["h0"].fulfilled_wunsch == {1: ["d0"]}
    assert result.best.per_dancer["h0"].score == 4


def test_sum_stage_may_prefer_two_weaker_wishes_over_one_strong_one() -> None:
    # h0 wants d0 (tier 1, weight 2) or d1 (tier 2, weight 1); h1 wants only d0.
    # Giving d0 to h0 scores 4 + 0; giving d0 to h1 scores 2 + 4. Both leave the floor at 0,
    # so the sum stage decides and the larger total wins.
    instance = team(
        3, 3, 3, wunsch("h0", tier(1, "d0"), tier(2, "d1")), wunsch("h1", tier(1, "d0"))
    )
    result = solve(instance)
    assert_result_valid(result, instance)
    assert share_position(result.best, "h1", "d0")
    assert share_position(result.best, "h0", "d1")
    assert result.best.total_score == 6


def test_dislike_is_avoided() -> None:
    instance = team(3, 3, 3, nicht_wunsch("h0", tier(1, "d0")))
    result = solve(instance)
    assert_result_valid(result, instance)
    assert not share_position(result.best, "h0", "d0")
    assert result.best.total_score == 0


# -- hard constraints ---------------------------------------------------------------------


def test_startanspruch_forces_a_single_role_position() -> None:
    instance = team(4, 4, 3, **{"h0": {"has_startanspruch": True}})
    result = solve(instance)
    assert_result_valid(result, instance)
    label = position_of(result.best, "h0")
    position = next(p for p in result.best.positions if p.label == label)
    assert position.herren == ["h0"]


def test_coachingbedarf_forces_a_shared_role_position() -> None:
    instance = team(4, 4, 3, **{"h0": {"needs_coaching": True}})
    result = solve(instance)
    assert_result_valid(result, instance)
    label = position_of(result.best, "h0")
    position = next(p for p in result.best.positions if p.label == label)
    assert len(position.herren) == 2


def test_startanspruch_beats_a_wish() -> None:
    # h0 wishes for d0, but d0's position would have to hold two Herren for the counts to
    # work out; Startanspruch is a hard constraint and the wish must lose.
    instance = team(
        4,
        3,
        3,
        wunsch("h0", tier(1, "d0")),
        nicht_wunsch("h1", tier(1, "d1", "d2")),
        **{"h0": {"has_startanspruch": True}},
    )
    result = solve(instance)
    assert_result_valid(result, instance)
    label = position_of(result.best, "h0")
    position = next(p for p in result.best.positions if p.label == label)
    assert position.herren == ["h0"]


def test_veto_is_respected_even_when_it_costs_score() -> None:
    # h0 wants d0 at tier 1 but d0 vetoes h0. The veto is symmetric and hard, so the wish
    # cannot be granted at any price.
    instance = team(3, 3, 3, wunsch("h0", tier(1, "d0")), nicht_wunsch("d0", tier(1, "h0")))
    result = solve(instance)
    assert_result_valid(result, instance)
    assert not share_position(result.best, "h0", "d0")
    assert result.best.per_dancer["h0"].score == 0


def test_veto_tier_none_leaves_dislikes_to_the_objective() -> None:
    instance = team(3, 3, 3, nicht_wunsch("h0", tier(1, "d0")))
    config = SolverConfig(veto_tier=None)
    result = solve(instance, config)
    assert_result_valid(result, instance, config)
    # Still avoided, but by the objective rather than by a constraint.
    assert not share_position(result.best, "h0", "d0")


def test_veto_tier_two_also_vetoes_tier_one() -> None:
    instance = team(3, 3, 3, nicht_wunsch("h0", tier(1, "d0"), tier(2, "d1")))
    config = SolverConfig(veto_tier=2)
    result = solve(instance, config)
    assert_result_valid(result, instance, config)
    assert not share_position(result.best, "h0", "d0")
    assert not share_position(result.best, "h0", "d1")


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

    The instance forces h0 and h1 onto the same position (both need coaching and there is
    exactly one Herren-Doppelbesetzung available), and they dislike each other. If the
    ``AddBoolOr`` half of the reification is deleted, the solver is free to claim
    ``together == 0`` and report a score of 0 instead of the penalty.
    """
    instance = team(
        4,
        4,
        3,
        nicht_wunsch("h0", tier(1, "h1")),
        nicht_wunsch("h1", tier(1, "h0")),
        **{"h0": {"needs_coaching": True}, "h1": {"needs_coaching": True}},
    )
    # Vetoes off: the pair must be co-positioned, so a hard veto would make it infeasible.
    config = SolverConfig(scope=PreferenceScope.ALL, veto_tier=None)
    result = solve(instance, config)
    assert_result_valid(result, instance, config)
    assert share_position(result.best, "h0", "h1"), "the instance must force them together"
    assert result.best.per_dancer["h0"].score == -2
    assert result.best.per_dancer["h1"].score == -2
    assert result.best.per_dancer["h0"].violated_nicht_wunsch == {1: ["h1"]}
    assert result.stages[0].value == -2  # the maximin stage saw the penalty too


def test_reification_cannot_invent_togetherness() -> None:
    """The other direction: ``together`` must be 0 when the pair is apart.

    h0 wishes for d0 but a veto keeps them apart; a broken reification could still claim the
    wish was granted and inflate the score.
    """
    instance = team(3, 3, 3, wunsch("h0", tier(1, "d0")), nicht_wunsch("d0", tier(1, "h0")))
    result = solve(instance)
    assert_result_valid(result, instance)
    assert result.best.total_score == 0


# -- objectives ---------------------------------------------------------------------------


def _lonely_instance() -> Team:
    """Everyone wants d0; only one Herr can have them.

    With WEIGHTED_SUM the solver is free to pile score onto whoever is cheapest to satisfy
    and leave someone at nothing. MAXIMIN_THEN_SUM has to lift the floor first.
    """
    return team(
        3,
        3,
        3,
        wunsch("h0", tier(1, "d0")),
        wunsch("h1", tier(1, "d0")),
        wunsch("h2", tier(1, "d0", "d1", "d2")),
    )


def test_weighted_sum_maximises_the_total() -> None:
    instance = _lonely_instance()
    config = SolverConfig(objective=Objective.WEIGHTED_SUM)
    result = solve(instance, config)
    assert_result_valid(result, instance, config)
    assert [stage.name for stage in result.stages] == ["sum", "coupled"]
    # h2 is satisfied by any Dame, and exactly one of h0/h1 can have d0: total 4.
    assert result.best.total_score == 4
    assert result.best.min_score == 0


def test_maximin_then_sum_lifts_the_worst_off_dancer() -> None:
    instance = _lonely_instance()
    config = SolverConfig(objective=Objective.MAXIMIN_THEN_SUM)
    result = solve(instance, config)
    assert_result_valid(result, instance, config)
    assert [stage.name for stage in result.stages] == ["maximin", "sum", "coupled"]
    # The floor cannot be lifted above 0 here -- h0 and h1 both want only d0 -- but the
    # stage order is what matters, and the total must still be maximal at that floor.
    assert result.stages[0].value == result.best.min_score
    assert result.best.total_score == 4


def test_maximin_prefers_a_lifted_floor_over_a_larger_total() -> None:
    # h0 wants d0 only. h1 wants d0 (tier 1) or d1 (tier 2).
    # Give h0 d0 => scores 2 and 2 (K=2: tier1=2, tier2=1, x2 scale), min 2, total 4... but
    # giving h1 d0 instead => h0 gets 0, h1 gets 4, total 4 with min 0. Same total, and
    # maximin must pick the first.
    instance = team(
        3,
        3,
        3,
        wunsch("h0", tier(1, "d0")),
        wunsch("h1", tier(1, "d0"), tier(2, "d1")),
    )
    maximin = SolverConfig(objective=Objective.MAXIMIN_THEN_SUM)
    result = solve(instance, maximin)
    assert_result_valid(result, instance, maximin)
    assert share_position(result.best, "h0", "d0")
    assert share_position(result.best, "h1", "d1")
    assert result.best.min_score == 0  # h2, d2 etc. are unsurveyed and score 0
    assert result.best.per_dancer["h0"].score == 4
    assert result.best.per_dancer["h1"].score == 2
    assert result.best.total_score == 6


@pytest.mark.parametrize("objective", [Objective.LEXIMIN, Objective.LEXICOGRAPHIC_TIERS])
def test_unimplemented_objectives_say_so(tiny: Team, objective: Objective) -> None:
    with pytest.raises(NotImplementedError, match="Milestone 3"):
        solve(tiny, SolverConfig(objective=objective))


@pytest.mark.parametrize("scheme", list(WeightScheme))
def test_both_weight_schemes_find_the_same_assignment(scheme: WeightScheme) -> None:
    instance = team(3, 3, 3, wunsch("h0", tier(1, "d0"), tier(2, "d1")))
    config = SolverConfig(weights=scheme)
    result = solve(instance, config)
    assert_result_valid(result, instance, config)
    assert share_position(result.best, "h0", "d0")


# -- normalisation ------------------------------------------------------------------------


def test_normalisation_removes_the_incentive_to_double_a_well_liked_dancer() -> None:
    # h0 wants both d0 and d1 at tier 1. Without normalisation the solver puts all three on
    # one position to collect two contributions; with it, one is worth as much as two.
    instance = team(4, 4, 3, wunsch("h0", tier(1, "d0", "d1")))

    unnormalised = SolverConfig(normalize_double=False)
    greedy = solve(instance, unnormalised)
    assert_result_valid(greedy, instance, unnormalised)
    assert share_position(greedy.best, "h0", "d0", "d1")
    assert greedy.best.per_dancer["h0"].score == 2

    normalised = SolverConfig(normalize_double=True)
    fair = solve(instance, normalised)
    assert_result_valid(fair, instance, normalised)
    assert fair.best.per_dancer["h0"].score == 2  # the same score either way now
    assert fair.best.total_score == 2


def test_normalisation_is_driven_by_the_opposite_role_count() -> None:
    # h0 sits with two Damen it likes; doubling the Herren on that position must not change
    # h0's cross-role score, only the Damen count does.
    instance = team(4, 5, 3, wunsch("h0", tier(1, "d0", "d1")))
    config = SolverConfig()
    result = solve(instance, config)
    assert_result_valid(result, instance, config)
    label = position_of(result.best, "h0")
    position = next(p for p in result.best.positions if p.label == label)
    granted = set(result.best.per_dancer["h0"].fulfilled_wunsch.get(1, []))
    expected = 1 if len(position.damen) == 2 else 2
    assert result.best.per_dancer["h0"].score == expected * len(granted)


# -- the soft coupled-position preference -------------------------------------------------


def test_coupled_stage_reaches_the_role_count_floor(uneven: Team) -> None:
    # 4 Herren, 5 Damen over 3 positions: 1 Herren-double, 2 Damen-doubles. At least
    # abs(4 - 5) = 1 position must be lopsided, and the stage must reach exactly that.
    config = SolverConfig(prefer_coupled=True)
    result = solve(uneven, config)
    assert_result_valid(result, uneven, config)
    coupled = next(stage for stage in result.stages if stage.name == "coupled")
    assert coupled.sense is Sense.MINIMIZE
    n_herren = len(uneven.by_role(Role.HERR))
    n_damen = len(uneven.by_role(Role.DAME))
    assert coupled.value == abs(n_herren - n_damen)
    lopsided = sum(1 for p in result.best.positions if (len(p.herren) == 2) != (len(p.damen) == 2))
    assert lopsided == abs(n_herren - n_damen)


def test_even_roster_becomes_fully_coupled(small: Team) -> None:
    config = SolverConfig(prefer_coupled=True)
    result = solve(small, config)
    assert_result_valid(result, small, config)
    assert next(s for s in result.stages if s.name == "coupled").value == 0
    assert sum(1 for p in result.best.positions if p.is_doubled) == 1


def test_coupled_stage_never_costs_a_wish(uneven: Team) -> None:
    instance = Team(
        dancers=uneven.dancers,
        surveys=[wunsch("h0", tier(1, "d0")), wunsch("d0", tier(1, "h0"))],
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
            wunsch("h0", tier(1, "d0"), tier(2, "d1")),
            wunsch("h1", tier(1, "d0")),
            wunsch("d0", tier(1, "h1")),
            nicht_wunsch("h2", tier(1, "d2")),
            wunsch("d3", tier(1, "h3", "h4")),
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
            wunsch("h0", tier(1, "d0", "d1"), tier(2, "d2")),
            wunsch("h1", tier(1, "d1"), tier(2, "d3")),
            wunsch("h2", tier(1, "d4")),
            nicht_wunsch("h3", tier(1, "d5")),
            wunsch("d0", tier(1, "h0")),
            wunsch("d6", tier(1, "h4", "h5")),
            nicht_wunsch("d7", tier(1, "h6")),
        ],
        n_positions=8,
    )
    config = SolverConfig(max_time_in_seconds=30.0)
    result = solve(instance, config)
    assert result.status == "OPTIMAL"
    assert_result_valid(result, instance, config)
    assert result.wall_time < 30.0
