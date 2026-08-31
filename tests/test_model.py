"""One test per validator in SPEC.md 6, each asserting the specific error."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from dancepartner.model import (
    Dancer,
    PreferenceScope,
    Role,
    SolverConfig,
    Survey,
    Team,
    Tier,
    position_label,
    position_labels,
)

from .builders import follower, leader, roster, tier


def test_validator_1_flags_are_mutually_exclusive() -> None:
    with pytest.raises(ValidationError, match="mutually exclusive"):
        Dancer(id="led0", name="LED0", role=Role.LEADER, is_pole_position=True, needs_coaching=True)


@pytest.mark.parametrize("direction", ["desired_tiers", "not_desired_tiers"])
@pytest.mark.parametrize(
    "ranks",
    [
        pytest.param([2], id="does-not-start-at-1"),
        pytest.param([1, 3], id="gap"),
        pytest.param([1, 1], id="duplicate"),
    ],
)
def test_validator_2_tier_ranks_are_contiguous(direction: str, ranks: list[int]) -> None:
    tiers = [Tier(rank=rank, dancer_ids=frozenset({f"x{i}"})) for i, rank in enumerate(ranks)]
    with pytest.raises(ValidationError, match="contiguous"):
        Survey(dancer_id="led0", **{direction: tiers})


def test_validator_3_id_in_at_most_one_tier_per_direction() -> None:
    with pytest.raises(ValidationError, match="more than one desired tier"):
        Survey(dancer_id="led0", desired_tiers=[tier(1, "fol0"), tier(2, "fol0", "fol1")])


def test_validator_4_id_in_at_most_one_direction() -> None:
    with pytest.raises(ValidationError, match="both desired and not_desired"):
        Survey(
            dancer_id="led0", desired_tiers=[tier(1, "fol0")], not_desired_tiers=[tier(1, "fol0")]
        )


@pytest.mark.parametrize("direction", ["desired_tiers", "not_desired_tiers"])
def test_validator_5_no_self_reference(direction: str) -> None:
    with pytest.raises(ValidationError, match="self-reference"):
        Survey(dancer_id="led0", **{direction: [tier(1, "led0")]})


def test_validator_6_referenced_ids_must_exist() -> None:
    with pytest.raises(ValidationError, match=r"unknown dancer ids \['ghost'\]"):
        Team(
            dancers=roster(3, 3),
            surveys=[Survey(dancer_id="led0", desired_tiers=[tier(1, "ghost")])],
        )


def test_validator_6_survey_subject_must_exist() -> None:
    with pytest.raises(ValidationError, match="unknown dancer id 'ghost'"):
        Team(dancers=roster(3, 3), surveys=[Survey(dancer_id="ghost")])


def test_validator_6_rejects_duplicate_dancer_ids() -> None:
    with pytest.raises(ValidationError, match=r"duplicate dancer ids: \['led0'\]"):
        Team(dancers=[leader("led0"), leader("led0"), follower("fol0")], n_positions=1)


def test_validator_7_at_most_one_survey_per_dancer() -> None:
    with pytest.raises(ValidationError, match=r"more than one survey for dancer ids: \['led0'\]"):
        Team(dancers=roster(3, 3), surveys=[Survey(dancer_id="led0"), Survey(dancer_id="led0")])


def test_empty_tier_is_rejected() -> None:
    with pytest.raises(ValidationError, match="at least one dancer"):
        Tier(rank=1, dancer_ids=frozenset())


def test_valid_team_round_trips(tiny: Team) -> None:
    assert len(tiny.dancers) == 6
    assert [d.id for d in tiny.by_role(Role.LEADER)] == ["led0", "led1", "led2"]
    assert tiny.dancers_by_id["led0"].name == "LED0"


# -- derived views ------------------------------------------------------------------------


def test_positions_are_labelled_a_to_h() -> None:
    assert position_labels(8) == list("ABCDEFGH")
    assert position_label(7) == "H"
    with pytest.raises(ValueError, match="must be positive"):
        position_labels(0)


def test_position_labels_beyond_z() -> None:
    assert position_labels(28)[26:] == ["AA", "AB"]


def test_role_opposite() -> None:
    assert Role.LEADER.opposite is Role.FOLLOWER
    assert Role.FOLLOWER.opposite is Role.LEADER


def test_doubling_counts_are_per_role(uneven: Team) -> None:
    # 4 Herren over 3 positions: one doubled, two single. 5 Damen: two doubled, one single.
    assert uneven.n_doubled_positions(Role.LEADER) == 1
    assert uneven.n_single_positions(Role.LEADER) == 2
    assert uneven.n_doubled_positions(Role.FOLLOWER) == 2
    assert uneven.n_single_positions(Role.FOLLOWER) == 1


def test_max_rank_is_instance_global() -> None:
    team = Team(
        dancers=roster(3, 3),
        surveys=[
            Survey(dancer_id="led0", desired_tiers=[tier(1, "fol0")]),
            Survey(dancer_id="led1", desired_tiers=[tier(1, "fol1"), tier(2, "fol2")]),
        ],
        n_positions=3,
    )
    assert team.max_rank == 2
    assert Team(dancers=roster(3, 3), n_positions=3).max_rank == 0


def test_preference_entries_respect_scope() -> None:
    team = Team(
        dancers=roster(3, 3),
        surveys=[Survey(dancer_id="led0", desired_tiers=[tier(1, "fol0", "led1")])],
        n_positions=3,
    )
    cross = {(e.source, e.target) for e in team.preference_entries(PreferenceScope.CROSS_ROLE_ONLY)}
    assert cross == {("led0", "fol0")}
    every = {(e.source, e.target) for e in team.preference_entries(PreferenceScope.ALL)}
    assert every == {("led0", "fol0"), ("led0", "led1")}


def test_preferences_are_directed_not_symmetrised() -> None:
    team = Team(
        dancers=roster(3, 3),
        surveys=[Survey(dancer_id="led0", desired_tiers=[tier(1, "fol0")])],
        n_positions=3,
    )
    entries = list(team.preference_entries(PreferenceScope.CROSS_ROLE_ONLY))
    assert [(e.source, e.target) for e in entries] == [("led0", "fol0")]


def test_survey_rank_lookup() -> None:
    survey = Survey(
        dancer_id="led0",
        desired_tiers=[tier(1, "fol0"), tier(2, "fol1")],
        not_desired_tiers=[tier(1, "fol2")],
    )
    assert survey.rank_of("fol0", "desired") == 1
    assert survey.rank_of("fol1", "desired") == 2
    assert survey.rank_of("fol2", "desired") is None
    assert survey.rank_of("fol2", "not_desired") == 1
    assert survey.named_ids("desired") == frozenset({"fol0", "fol1"})
    assert Survey(dancer_id="led0").named_ids("desired") == frozenset()
    assert Survey(dancer_id="led0").max_rank == 0


# -- config ------------------------------------------------------------------------------


def test_solver_config_veto_tier_must_be_positive_or_none() -> None:
    with pytest.raises(ValidationError, match="veto_tier must be"):
        SolverConfig(veto_tier=0)
    assert SolverConfig(veto_tier=None).veto_tier is None


def test_solver_config_vetoed_ranks() -> None:
    config = SolverConfig(veto_tier=2)
    assert config.vetoed_ranks(1)
    assert config.vetoed_ranks(2)
    assert not config.vetoed_ranks(3)
    assert not SolverConfig(veto_tier=None).vetoed_ranks(1)


def test_score_scale_follows_normalisation() -> None:
    assert SolverConfig(normalize_double=True).score_scale == 2
    assert SolverConfig(normalize_double=False).score_scale == 1
