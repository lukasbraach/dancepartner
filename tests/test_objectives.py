"""LEXIMIN and LEXICOGRAPHIC_TIERS: the objectives that arrived with Milestone 3.

The point of both is that they disagree with ``MAXIMIN_THEN_SUM`` in ways the coach cares
about, so the tests assert the disagreement, not just that they run.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from dancepartner.model import Objective, ScoreAggregation, SolverConfig, Team
from dancepartner.scoring import DancerSatisfaction
from dancepartner.solver import Sense, SolveResult, solve
from dancepartner.storage import load_team

from .builders import desired, not_desired, team, tier
from .helpers import assert_leximin_vector, assert_result_valid, stage_expectation

EXAMPLE = Path(__file__).resolve().parents[1] / "data" / "team.example.yaml"


def _score_vector(per_dancer: dict[str, DancerSatisfaction]) -> list[int]:
    """The sorted-ascending score vector -- the thing leximin actually optimises."""
    return sorted(satisfaction.score for satisfaction in per_dancer.values())


# -- LEXIMIN ------------------------------------------------------------------------------


def divergent_instance() -> Team:
    """An instance where maximising the total and levelling up disagree.

    3 Herren, 4 Damen, 3 positions. Under ``ScoreAggregation.SUM`` (the divergence test pins
    it -- the hand-derived vectors are summed arithmetic), ``MAXIMIN_THEN_SUM`` reaches a
    total of 26 with the score vector ``[0, 0, 2, 6, 6, 6, 6]`` -- two dancers with nothing.
    ``LEXIMIN`` gives up five points of total to reach ``[0, 2, 2, 3, 4, 4, 6]``, which is
    lexicographically better from the bottom: same worst score, but the second-worst rises
    from 0 to 2.
    """
    return team(
        3,
        4,
        3,
        desired("led0", tier(1, "fol2")),
        desired("led1", tier(1, "fol3"), tier(2, "fol2"), tier(3, "fol0")),
        desired("led2", tier(1, "fol3")),
        desired("fol0", tier(1, "led0"), tier(2, "led1"), tier(3, "led2")),
        desired("fol1", tier(1, "led1"), tier(2, "led2"), tier(3, "led0")),
        desired("fol2", tier(1, "led1"), tier(2, "led2"), tier(3, "led0")),
    )


def test_leximin_levels_up_where_maximin_then_sum_concentrates() -> None:
    instance = divergent_instance()
    sum_config = SolverConfig(
        objective=Objective.MAXIMIN_THEN_SUM,
        aggregation=ScoreAggregation.SUM,
        max_solutions=1,
    )
    lex_config = SolverConfig(
        objective=Objective.LEXIMIN, aggregation=ScoreAggregation.SUM, max_solutions=1
    )

    greedy = solve(instance, sum_config)
    levelled = solve(instance, lex_config)
    assert_result_valid(greedy, instance, sum_config)
    assert_result_valid(levelled, instance, lex_config)

    greedy_vector = _score_vector(greedy.best.per_dancer)
    levelled_vector = _score_vector(levelled.best.per_dancer)
    assert greedy_vector == [0, 0, 2, 6, 6, 6, 6]
    assert levelled_vector == [0, 2, 2, 3, 4, 4, 6]

    # Same floor, but leximin leaves only one dancer on it instead of two.
    assert greedy.best.min_score == levelled.best.min_score == 0
    assert greedy_vector.count(0) == 2
    assert levelled_vector.count(0) == 1
    # And it pays for that in total score, which is the whole trade.
    assert levelled.best.total_score < greedy.best.total_score
    # Lexicographically better read from the bottom up.
    assert levelled_vector > greedy_vector


def test_leximin_is_never_worse_on_the_sorted_vector() -> None:
    instance = divergent_instance()
    vectors = {}
    for objective in (Objective.WEIGHTED_SUM, Objective.MAXIMIN_THEN_SUM, Objective.LEXIMIN):
        config = SolverConfig(objective=objective, max_solutions=1)
        result = solve(instance, config)
        assert_result_valid(result, instance, config)
        vectors[objective] = _score_vector(result.best.per_dancer)
    assert vectors[Objective.LEXIMIN] >= vectors[Objective.MAXIMIN_THEN_SUM]
    assert vectors[Objective.LEXIMIN] >= vectors[Objective.WEIGHTED_SUM]


def test_leximin_rounds_reconstruct_the_score_multiset() -> None:
    instance = divergent_instance()
    config = SolverConfig(objective=Objective.LEXIMIN, max_solutions=1)
    result = solve(instance, config)
    # The dedicated check, called explicitly here so the failure message points at it.
    assert_leximin_vector(result)

    rounds = [s for s in result.stages if s.name.startswith("leximin.")]
    floors = [s.value for s in rounds if s.name.endswith(".floor")]
    counts = [s.value for s in rounds if s.name.endswith(".count")]
    assert floors == sorted(floors), "each round's floor must be at least the previous one"
    assert floors == sorted(set(floors)), "a round must strictly raise the floor"
    assert counts == sorted(counts, reverse=True), "the active set only ever shrinks"
    assert counts[-1] == 0, "the last round leaves nobody above its floor"


def test_leximin_needs_no_sum_stage() -> None:
    # The rounds pin the whole sorted vector, so the total is already determined and a `sum`
    # stage would be dead weight.
    result = solve(divergent_instance(), SolverConfig(objective=Objective.LEXIMIN))
    assert [s.name for s in result.stages if s.name == "sum"] == []
    totals = {s.total_score for s in result.solutions}
    assert len(totals) == 1, "every leximin optimum must have the same total"


def test_leximin_terminates_on_an_instance_with_no_preferences(tiny: Team) -> None:
    config = SolverConfig(objective=Objective.LEXIMIN)
    result = solve(tiny, config)
    assert_result_valid(result, tiny, config)
    # Everyone scores 0, so one round settles it.
    rounds = [s for s in result.stages if s.name.startswith("leximin.")]
    assert len(rounds) == 2
    assert rounds[0].value == 0
    assert rounds[1].value == 0


def test_leximin_respects_the_hard_constraints() -> None:
    instance = team(
        4,
        4,
        3,
        desired("led0", tier(1, "fol0")),
        not_desired("led1", tier(1, "fol1")),
        **{"led0": {"is_pole_position": True}, "led2": {"needs_coaching": True}},
    )
    config = SolverConfig(objective=Objective.LEXIMIN)
    result = solve(instance, config)
    assert_result_valid(result, instance, config)


# -- LEXICOGRAPHIC_TIERS -------------------------------------------------------------------


def test_tier_objective_fulfils_more_tier_one_wishes_than_the_weighted_ones() -> None:
    # A tier-1 wish is worth 2 and a tier-2 wish 1, so a weighted objective will happily trade
    # one tier-1 fulfilment for two tier-2 ones. LEXICOGRAPHIC_TIERS refuses to.
    instance = team(
        3,
        3,
        3,
        desired("led0", tier(1, "fol0")),
        desired("led1", tier(1, "fol1")),
        desired("fol0", tier(1, "led1")),
        desired("fol1", tier(1, "led0")),
        desired("led2", tier(1, "fol2")),
    )
    counts = {}
    for objective in (Objective.WEIGHTED_SUM, Objective.LEXICOGRAPHIC_TIERS):
        config = SolverConfig(objective=objective, max_solutions=1)
        result = solve(instance, config)
        assert_result_valid(result, instance, config)
        counts[objective] = sum(
            len(s.fulfilled_desired.get(1, [])) for s in result.best.per_dancer.values()
        )
    assert counts[Objective.LEXICOGRAPHIC_TIERS] >= counts[Objective.WEIGHTED_SUM]


def test_tier_stages_are_ordered_wishes_then_dislikes() -> None:
    instance = team(
        3,
        3,
        3,
        desired("led0", tier(1, "fol0"), tier(2, "fol1")),
        not_desired("led1", tier(1, "fol2"), tier(2, "fol0")),
    )
    config = SolverConfig(objective=Objective.LEXICOGRAPHIC_TIERS, veto_tier=None)
    result = solve(instance, config)
    assert_result_valid(result, instance, config)
    names = [s.name for s in result.stages]
    assert names == [
        "desired.tier1",
        "desired.tier2",
        "not_desired.tier1",
        "not_desired.tier2",
        "coupled",
    ]
    senses = {s.name: s.sense for s in result.stages}
    assert senses["desired.tier1"] is Sense.MAXIMIZE
    assert senses["not_desired.tier1"] is Sense.MINIMIZE


def test_tier_objective_prefers_a_strong_wish_over_two_weak_ones() -> None:
    # led0 can sit with fol0 (its tier-1 wish) or with fol1+fol2 (two tier-2 wishes). Counting tiers
    # lexicographically means the single tier-1 fulfilment wins.
    instance = team(
        4,
        4,
        3,
        desired("led0", tier(1, "fol0"), tier(2, "fol1", "fol2")),
    )
    config = SolverConfig(objective=Objective.LEXICOGRAPHIC_TIERS, max_solutions=1)
    result = solve(instance, config)
    assert_result_valid(result, instance, config)
    assert result.best.per_dancer["led0"].fulfilled_desired.get(1) == ["fol0"]
    assert next(s for s in result.stages if s.name == "desired.tier1").value == 1


def test_tier_slack_lets_a_weaker_tier_buy_from_a_stronger_one() -> None:
    # 4 Herren and 4 Damen over 3 positions, so led0's position can hold two Damen. led0 wants fol0
    # at tier 1 and either of fol1/fol2 at tier 2.
    instance = team(
        4,
        4,
        3,
        desired("led0", tier(1, "fol0"), tier(2, "fol1", "fol2")),
    )
    strict = SolverConfig(objective=Objective.LEXICOGRAPHIC_TIERS, tier_slack=0, max_solutions=1)
    slack = SolverConfig(objective=Objective.LEXICOGRAPHIC_TIERS, tier_slack=1, max_solutions=1)
    tight = solve(instance, strict)
    loose = solve(instance, slack)
    assert_result_valid(tight, instance, strict)
    assert_result_valid(loose, instance, slack)

    def stage_value(result: SolveResult, name: str) -> int:
        return next(s.value for s in result.stages if s.name == name)

    # Strictly: fol0 at tier 1 plus one of fol1/fol2 at tier 2.
    assert stage_value(tight, "desired.tier1") == 1
    assert stage_value(tight, "desired.tier2") == 1
    assert tight.best.per_dancer["led0"].fulfilled_desired == {1: ["fol0"], 2: ["fol1"]}

    # With one wish of slack, tier 2 is allowed to walk tier 1 back: led0 takes fol1 *and* fol2 and
    # gives up fol0 entirely. The tier-1 stage still reports its own optimum of 1 -- that is what
    # it achieved before the slack was spent -- and `locked_at` records the floor it kept.
    assert stage_value(loose, "desired.tier1") == 1
    assert stage_value(loose, "desired.tier2") == 2
    assert loose.best.per_dancer["led0"].fulfilled_desired == {2: ["fol1", "fol2"]}
    assert stage_expectation("desired.tier1", loose.best) == 0
    locked = {s.name: s.locked_at for s in loose.stages}
    assert locked["desired.tier1"] == 0
    assert locked["desired.tier2"] == 2
    # Nothing could degrade the strict run, so it records no locked-in floors at all.
    assert {s.locked_at for s in tight.stages} == {None}


def test_the_coupled_tie_break_cannot_spend_tier_slack() -> None:
    """``prefer_coupled`` must never cost a fulfilled wish, slack or no slack.

    Without the guard in ``solver._lock_in`` the coupled stage happily spends whatever epsilon
    the tier stages left lying around: it would pull led0 back to a single tier-2 partner to even
    out the Doppelbesetzungen, quietly undoing the trade the slack was granted for.
    """
    instance = team(4, 4, 3, desired("led0", tier(1, "fol0"), tier(2, "fol1", "fol2")))
    with_tie_break = SolverConfig(
        objective=Objective.LEXICOGRAPHIC_TIERS, tier_slack=1, prefer_coupled=True
    )
    without = SolverConfig(
        objective=Objective.LEXICOGRAPHIC_TIERS, tier_slack=1, prefer_coupled=False
    )
    coupled = solve(instance, with_tie_break)
    plain = solve(instance, without)
    assert_result_valid(coupled, instance, with_tie_break)
    assert_result_valid(plain, instance, without)

    for name in ("desired.tier1", "desired.tier2"):
        assert stage_expectation(name, coupled.best) == stage_expectation(name, plain.best), (
            f"the coupled tie-break changed {name}"
        )
    assert coupled.best.per_dancer["led0"].fulfilled_desired == {2: ["fol1", "fol2"]}


def test_tier_objective_has_no_stages_without_surveys(tiny: Team) -> None:
    config = SolverConfig(objective=Objective.LEXICOGRAPHIC_TIERS)
    result = solve(tiny, config)
    assert_result_valid(result, tiny, config)
    assert [s.name for s in result.stages] == ["coupled"]


def test_tier_objective_on_the_example_beats_the_weighted_one_on_tier_one() -> None:
    instance = load_team(EXAMPLE)
    counts = {}
    for objective in (Objective.MAXIMIN_THEN_SUM, Objective.LEXICOGRAPHIC_TIERS):
        config = SolverConfig(objective=objective, max_solutions=1)
        result = solve(instance, config)
        assert_result_valid(result, instance, config)
        counts[objective] = Counter(
            rank
            for s in result.best.per_dancer.values()
            for rank, ids in s.fulfilled_desired.items()
            for _ in ids
        )
    assert counts[Objective.LEXICOGRAPHIC_TIERS][1] == 15
    assert counts[Objective.MAXIMIN_THEN_SUM][1] == 14


@pytest.mark.parametrize("aggregation", list(ScoreAggregation))
@pytest.mark.parametrize("objective", list(Objective))
def test_every_objective_verifies_on_a_realistic_instance(
    full: Team, objective: Objective, aggregation: ScoreAggregation
) -> None:
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
    config = SolverConfig(objective=objective, aggregation=aggregation, max_solutions=5)
    result = solve(instance, config)
    assert result.status == "OPTIMAL"
    assert_result_valid(result, instance, config)
