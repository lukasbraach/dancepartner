"""Weight schemes and the independent satisfaction recomputation."""

from __future__ import annotations

import pytest

from dancepartner.model import PreferenceScope, SolverConfig, Team, WeightScheme
from dancepartner.scoring import (
    build_satisfaction,
    build_solution,
    build_weights,
    geometric_base,
    scored_pairs,
    tier_weight,
)

from .builders import nicht_wunsch, team, tier, wunsch


def test_linear_weights_use_the_instance_global_max_rank() -> None:
    instance = team(
        3,
        3,
        3,
        wunsch("h0", tier(1, "d0")),
        wunsch("h1", tier(1, "d1"), tier(2, "d2"), tier(3, "d0")),
    )
    weights = build_weights(instance, SolverConfig(weights=WeightScheme.LINEAR))
    # K = 3, so a tier-1 wish is worth 3 for everyone -- h0 is not scored lower for having
    # listed a single tier.
    assert weights[("h0", "d0")] == 3
    assert weights[("h1", "d1")] == 3
    assert weights[("h1", "d2")] == 2
    assert weights[("h1", "d0")] == 1


def test_dislikes_are_negative_and_symmetric_in_magnitude() -> None:
    instance = team(3, 3, 3, wunsch("h0", tier(1, "d0")), nicht_wunsch("h1", tier(1, "d0")))
    weights = build_weights(instance, SolverConfig())
    assert weights[("h0", "d0")] == 1
    assert weights[("h1", "d0")] == -1


def test_weights_are_directed() -> None:
    instance = team(3, 3, 3, wunsch("h0", tier(1, "d0")))
    weights = build_weights(instance, SolverConfig())
    assert ("h0", "d0") in weights
    assert ("d0", "h0") not in weights


def test_tier_weight_directly() -> None:
    assert tier_weight(1, "wunsch", 3, None) == 3
    assert tier_weight(3, "wunsch", 3, None) == 1
    assert tier_weight(1, "nicht_wunsch", 3, None) == -3
    assert tier_weight(1, "wunsch", 3, 5) == 25
    assert tier_weight(3, "wunsch", 3, 5) == 1


def test_geometric_base_is_computed_from_the_instance() -> None:
    instance = team(3, 3, 3, wunsch("h0", tier(1, "d0")))
    # 6 dancers, at most 2 cross-role partners each => 12 possible fulfilments, base 13.
    assert geometric_base(instance, SolverConfig()) == 13
    assert geometric_base(instance, SolverConfig(scope=PreferenceScope.ALL)) == 19


def test_geometric_one_stronger_tier_outranks_every_weaker_one() -> None:
    instance = team(
        3,
        3,
        3,
        wunsch("h0", tier(1, "d0"), tier(2, "d1")),
    )
    config = SolverConfig(weights=WeightScheme.GEOMETRIC)
    weights = build_weights(instance, config)
    max_weaker_fulfilments = (3 if config.scope is PreferenceScope.ALL else 2) * len(
        instance.dancers
    )
    assert geometric_base(instance, config) == max_weaker_fulfilments + 1
    assert weights[("h0", "d0")] > weights[("h0", "d1")] * max_weaker_fulfilments


def test_scope_filters_same_role_entries() -> None:
    instance = team(4, 4, 3, wunsch("h0", tier(1, "d0", "h1")))
    assert set(build_weights(instance, SolverConfig())) == {("h0", "d0")}
    assert set(build_weights(instance, SolverConfig(scope=PreferenceScope.ALL))) == {
        ("h0", "d0"),
        ("h0", "h1"),
    }


def test_scored_pairs_only_covers_pairs_that_matter() -> None:
    instance = team(3, 3, 3, wunsch("h0", tier(1, "d0")), nicht_wunsch("h1", tier(1, "d1")))
    assert scored_pairs(instance, SolverConfig()) == [
        frozenset({"d0", "h0"}),
        frozenset({"d1", "h1"}),
    ]


def test_scored_pairs_is_empty_without_surveys(tiny: Team) -> None:
    assert scored_pairs(tiny, SolverConfig()) == []


# -- satisfaction reporting ---------------------------------------------------------------


def test_satisfaction_splits_fulfilled_violated_and_neutral() -> None:
    instance = team(
        4,
        4,
        3,
        wunsch("h0", tier(1, "d0")),
        nicht_wunsch("h1", tier(1, "d1")),
    )
    groups = [["h0", "d0"], ["h1", "d1"], ["h2", "h3", "d2", "d3"]]
    result = build_satisfaction(instance, SolverConfig(veto_tier=None), groups)
    assert result["h0"].fulfilled_wunsch == {1: ["d0"]}
    assert result["h0"].neutral_partners == []
    assert result["h1"].violated_nicht_wunsch == {1: ["d1"]}
    assert result["h2"].neutral_partners == ["d2", "d3"]
    assert result["d0"].fulfilled_wunsch == {}
    assert result["d0"].neutral_partners == ["h0"]


def test_normalisation_halves_a_doubled_cross_role_score() -> None:
    instance = team(4, 4, 3, wunsch("h0", tier(1, "d0", "d1")))
    single = build_satisfaction(
        instance, SolverConfig(), [["h0", "d0"], ["h1", "d1"], ["h2", "h3", "d2", "d3"]]
    )
    doubled = build_satisfaction(
        instance, SolverConfig(), [["h0", "h1", "d0", "d1"], ["h2", "d2"], ["h3", "d3"]]
    )
    # One wish granted on the x2 scale is 2; two wishes on a Doppelbesetzung are also 2, so
    # the solver gains nothing from parking a well-liked dancer on a double.
    assert single["h0"].score == 2
    assert doubled["h0"].score == 2
    assert doubled["h0"].fulfilled_wunsch == {1: ["d0", "d1"]}


def test_without_normalisation_a_doubled_score_is_twice_as_large() -> None:
    instance = team(4, 4, 3, wunsch("h0", tier(1, "d0", "d1")))
    config = SolverConfig(normalize_double=False)
    single = build_satisfaction(
        instance, config, [["h0", "d0"], ["h1", "d1"], ["h2", "h3", "d2", "d3"]]
    )
    doubled = build_satisfaction(
        instance, config, [["h0", "h1", "d0", "d1"], ["h2", "d2"], ["h3", "d3"]]
    )
    assert single["h0"].score == 1
    assert doubled["h0"].score == 2


def test_same_role_scores_are_not_halved_by_cross_role_doubling() -> None:
    instance = team(4, 4, 3, wunsch("h0", tier(1, "h1")))
    config = SolverConfig(scope=PreferenceScope.ALL)
    result = build_satisfaction(
        instance, config, [["h0", "h1", "d0", "d1"], ["h2", "d2"], ["h3", "d3"]]
    )
    # A dancer never has more than one same-role partner, so that half of the score is
    # simply on the x2 scale.
    assert result["h0"].score == 2
    assert result["h0"].fulfilled_wunsch == {1: ["h1"]}


def test_build_solution_labels_positions_a_to_c(tiny: Team) -> None:
    solution = build_solution(tiny, SolverConfig(), [["h0", "d0"], ["h1", "d1"], ["h2", "d2"]])
    assert [p.label for p in solution.positions] == ["A", "B", "C"]
    assert solution.positions[0].herren == ["h0"]
    assert solution.positions[0].damen == ["d0"]
    assert solution.total_score == 0
    assert solution.min_score == 0


def test_position_is_doubled_only_when_both_roles_are(small: Team) -> None:
    solution = build_solution(
        small, SolverConfig(), [["h0", "h1", "d0", "d1"], ["h2", "d2"], ["h3", "d3"]]
    )
    assert solution.positions[0].is_doubled
    assert not solution.positions[1].is_doubled


def test_signature_ignores_position_labels(tiny: Team) -> None:
    config = SolverConfig()
    a = build_solution(tiny, config, [["h0", "d0"], ["h1", "d1"], ["h2", "d2"]])
    b = build_solution(tiny, config, [["h2", "d2"], ["h0", "d0"], ["h1", "d1"]])
    c = build_solution(tiny, config, [["h0", "d1"], ["h1", "d0"], ["h2", "d2"]])
    assert a.signature == b.signature
    assert a.signature != c.signature


def test_empty_solution_min_score_is_zero(tiny: Team) -> None:
    from dancepartner.scoring import Solution

    assert Solution(positions=[], total_score=0, min_score=0, per_dancer={}).min_score == 0


@pytest.mark.parametrize("scheme", list(WeightScheme))
def test_every_weight_scheme_produces_integers(scheme: WeightScheme) -> None:
    instance = team(3, 3, 3, wunsch("h0", tier(1, "d0"), tier(2, "d1")))
    weights = build_weights(instance, SolverConfig(weights=scheme))
    assert all(isinstance(weight, int) for weight in weights.values())
