"""Solution enumeration and deduplication.

Preference problems have many equal optima, so the tool produces a shortlist for the coach to
choose from rather than one mandated answer. These tests check that the shortlist is made of
genuinely distinct, genuinely optimal assignments, and that its caps hold.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dancepartner.model import Objective, PreferenceScope, SolverConfig, Team
from dancepartner.solver import solve
from dancepartner.storage import load_team

from .builders import desired, not_desired, roster, team, tier
from .helpers import assert_result_valid, assert_valid, stage_expectation

EXAMPLE = Path(__file__).resolve().parents[1] / "data" / "team.example.yaml"


@pytest.fixture
def unconstrained() -> Team:
    """10 Herren, 12 Damen, 8 positions, no surveys: every assignment is optimal."""
    return Team(dancers=roster(10, 12), n_positions=8)


def test_max_solutions_one_skips_enumeration(tiny: Team) -> None:
    config = SolverConfig(max_solutions=1)
    result = solve(tiny, config)
    assert len(result.solutions) == 1
    assert not result.truncated
    assert_result_valid(result, tiny, config)


def test_the_example_team_has_exactly_three_optima() -> None:
    instance = load_team(EXAMPLE)
    config = SolverConfig(max_solutions=200)
    result = solve(instance, config)
    assert_result_valid(result, instance, config)
    assert len(result.solutions) == 3
    assert not result.truncated, "200 is enough room, so nothing may be cut"
    # Equal optima means exactly that: identical scores, different assignments.
    assert {s.total_score for s in result.solutions} == {55}
    assert {s.min_score for s in result.solutions} == {0}
    assert len({s.signature for s in result.solutions}) == 3


def test_every_enumerated_solution_satisfies_every_hard_constraint() -> None:
    instance = load_team(EXAMPLE)
    config = SolverConfig(max_solutions=200)
    result = solve(instance, config)
    for solution in result.solutions:
        assert_valid(solution, instance, config)


def test_the_shortlist_is_capped_and_says_so(unconstrained: Team) -> None:
    config = SolverConfig(max_solutions=25)
    result = solve(unconstrained, config)
    assert len(result.solutions) == 25
    assert result.truncated, "an instance with no preferences has far more than 25 optima"
    assert_result_valid(result, unconstrained, config)


def test_the_cap_is_honoured_exactly(unconstrained: Team) -> None:
    for cap in (2, 7, 33):
        result = solve(unconstrained, SolverConfig(max_solutions=cap))
        assert len(result.solutions) == cap


def test_enumerated_solutions_are_deduplicated_by_signature(unconstrained: Team) -> None:
    result = solve(unconstrained, SolverConfig(max_solutions=40))
    signatures = [s.signature for s in result.solutions]
    assert len(set(signatures)) == len(signatures)


def test_enumeration_is_deterministic() -> None:
    instance = load_team(EXAMPLE)
    config = SolverConfig(max_solutions=50, random_seed=3)
    first = solve(instance, config)
    second = solve(instance, config)
    assert [s.signature for s in first.solutions] == [s.signature for s in second.solutions]
    assert first.solutions == second.solutions


def test_the_first_solution_is_the_best_one() -> None:
    instance = load_team(EXAMPLE)
    config = SolverConfig(max_solutions=200, near_optimal_ratio=0.95)
    result = solve(instance, config)
    assert_result_valid(result, instance, config)
    # MAXIMIN_THEN_SUM ranks fairness first, then the total.
    keys = [(-s.min_score, -s.total_score) for s in result.solutions]
    assert keys == sorted(keys)
    assert result.best is result.solutions[0]
    assert result.best.total_score == max(s.total_score for s in result.solutions)


# -- near-optimal tolerance ---------------------------------------------------------------


def test_ratio_one_admits_only_exact_optima() -> None:
    instance = load_team(EXAMPLE)
    result = solve(instance, SolverConfig(max_solutions=200, near_optimal_ratio=1.0))
    assert {s.total_score for s in result.solutions} == {55}


@pytest.mark.parametrize(
    ("ratio", "expected_totals"),
    [
        pytest.param(1.0, {55}, id="exact"),
        pytest.param(0.98, {54, 55}, id="one-off"),
        pytest.param(0.95, {53, 54, 55}, id="two-off"),
    ],
)
def test_a_looser_ratio_widens_the_shortlist(ratio: float, expected_totals: set[int]) -> None:
    instance = load_team(EXAMPLE)
    config = SolverConfig(max_solutions=200, near_optimal_ratio=ratio)
    result = solve(instance, config)
    assert_result_valid(result, instance, config)
    assert {s.total_score for s in result.solutions} == expected_totals


def test_a_looser_ratio_never_shrinks_the_shortlist() -> None:
    instance = load_team(EXAMPLE)
    counts = [
        len(solve(instance, SolverConfig(max_solutions=500, near_optimal_ratio=r)).solutions)
        for r in (1.0, 0.98, 0.95)
    ]
    assert counts == sorted(counts)


def test_the_slack_widens_a_negative_optimum_instead_of_tightening_it() -> None:
    # A forced, mutually disliked pair drives the total negative. Taking 0.9 * optimum
    # literally would demand a *better* score than the optimum and return nothing.
    instance = team(
        4,
        4,
        3,
        not_desired("led0", tier(1, "led1")),
        not_desired("led1", tier(1, "led0")),
        **{"led0": {"needs_coaching": True}, "led1": {"needs_coaching": True}},
    )
    config = SolverConfig(
        scope=PreferenceScope.ALL,
        veto_tier=None,
        max_solutions=50,
        near_optimal_ratio=0.5,
    )
    result = solve(instance, config)
    assert result.best.total_score < 0
    assert_result_valid(result, instance, config)
    assert len(result.solutions) >= 1


# -- interaction with the rest of the model ------------------------------------------------


@pytest.mark.parametrize("objective", list(Objective))
def test_enumeration_works_for_every_objective(objective: Objective) -> None:
    instance = load_team(EXAMPLE)
    config = SolverConfig(objective=objective, max_solutions=20)
    result = solve(instance, config)
    assert result.solutions
    assert_result_valid(result, instance, config)


def test_leximin_optima_all_share_one_score_vector() -> None:
    instance = load_team(EXAMPLE)
    config = SolverConfig(objective=Objective.LEXIMIN, max_solutions=50)
    result = solve(instance, config)
    assert_result_valid(result, instance, config)
    vectors = {
        tuple(sorted(s.score for s in solution.per_dancer.values()))
        for solution in result.solutions
    }
    assert len(vectors) == 1, "the leximin rounds pin the whole vector, so it cannot vary"


def test_enumeration_respects_pole_position_and_coaching() -> None:
    instance = team(
        6,
        7,
        4,
        desired("led0", tier(1, "fol0")),
        **{
            "led0": {"is_pole_position": True},
            "led1": {"needs_coaching": True},
            "fol0": {"is_pole_position": True},
        },
    )
    config = SolverConfig(max_solutions=30)
    result = solve(instance, config)
    assert len(result.solutions) > 1, "this instance has more than one optimum"
    assert_result_valid(result, instance, config)


def test_enumeration_respects_hard_vetoes() -> None:
    instance = team(6, 7, 4, not_desired("led0", tier(1, "fol0", "fol1")))
    config = SolverConfig(max_solutions=30)
    result = solve(instance, config)
    for solution in result.solutions:
        for position in solution.positions:
            here = {*position.leaders, *position.followers}
            assert not {"led0", "fol0"} <= here
            assert not {"led0", "fol1"} <= here
    assert_result_valid(result, instance, config)


def test_no_solutions_when_the_instance_is_infeasible() -> None:
    instance = team(3, 8, 8)
    result = solve(instance, SolverConfig(max_solutions=50), skip_precheck=True)
    assert result.status == "INFEASIBLE"
    assert result.solutions == []
    assert not result.truncated


def test_dedup_survives_symmetry_breaking_being_off() -> None:
    """Without the canonical numbering, one partition reaches the callback many times over.

    2 positions, 2 Herren, 2 Damen: there are exactly two ways to pair them up, but four ways
    to *label* those pairings across positions A and B. CP-SAT reports all four, and only the
    signature -- the frozenset of frozensets SPEC.md 8 asks for -- collapses them back to two.
    """
    instance = Team(dancers=roster(2, 2), n_positions=2)
    config = SolverConfig(max_solutions=10)

    canonical = solve(instance, config, break_symmetry=True)
    assert len(canonical.solutions) == 2
    assert not canonical.truncated

    free = solve(instance, config, break_symmetry=False)
    signatures = [s.signature for s in free.solutions]
    assert len(set(signatures)) == len(signatures), "the dedup let a relabelling through"
    assert len(free.solutions) == 2, "the four labellings must collapse to two solutions"
    assert {s.signature for s in free.solutions} == {s.signature for s in canonical.solutions}
    assert_result_valid(free, instance, config)


def test_dedup_holds_on_a_larger_unconstrained_instance(unconstrained: Team) -> None:
    config = SolverConfig(max_solutions=30)
    result = solve(unconstrained, config, break_symmetry=False)
    signatures = [s.signature for s in result.solutions]
    assert len(set(signatures)) == len(signatures)
    assert_result_valid(result, unconstrained, config)


def test_tier_slack_is_locked_before_the_shortlist_is_enumerated() -> None:
    """A MINIMIZE stage's slack must be locked too, not just a MAXIMIZE one.

    The dislike tiers minimise violations, so this is the mirror image of the tier-1/tier-2
    trade: once the stage sequence ends, no shortlist entry may quietly violate one more
    dislike than the stages settled on.
    """
    instance = team(
        6,
        7,
        4,
        desired("led0", tier(1, "fol0"), tier(2, "fol1")),
        not_desired("led1", tier(1, "fol2"), tier(2, "fol3")),
        not_desired("fol4", tier(1, "led2"), tier(2, "led3")),
    )
    config = SolverConfig(
        objective=Objective.LEXICOGRAPHIC_TIERS,
        tier_slack=1,
        veto_tier=None,
        max_solutions=20,
    )
    result = solve(instance, config)
    assert len(result.solutions) > 1, "this instance must have several optima to be a real test"
    assert_result_valid(result, instance, config)

    # Every entry of the shortlist must respect the locked-in dislike counts.
    for stage in result.stages:
        if not stage.name.startswith("not_desired."):
            continue
        target = stage.value if stage.locked_at is None else stage.locked_at
        for solution in result.solutions:
            assert stage_expectation(stage.name, solution) <= target
