"""Counting pre-checks, including the exact boundary cases."""

from __future__ import annotations

import pytest

from dancepartner.feasibility import check_feasibility, together_components, veto_pairs
from dancepartner.model import CoachConstraints, PreferenceScope, Role, SolverConfig, Team

from .builders import apart, not_desired, roster, team, tier, together, with_coach


def codes(team_: Team, config: SolverConfig | None = None) -> list[str]:
    return [issue.code for issue in check_feasibility(team_, config)]


def test_clean_instance_has_no_issues(small: Team) -> None:
    assert check_feasibility(small) == []


# -- role counts -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("n_leaders", "n_followers", "n_positions", "expected"),
    [
        pytest.param(8, 8, 8, [], id="n=P-lower-boundary"),
        pytest.param(16, 16, 8, [], id="n=2P-upper-boundary"),
        pytest.param(7, 8, 8, ["ROLE_COUNT_OUT_OF_RANGE"], id="too-few-leaders"),
        pytest.param(17, 8, 8, ["ROLE_COUNT_OUT_OF_RANGE"], id="too-many-leaders"),
        pytest.param(8, 7, 8, ["ROLE_COUNT_OUT_OF_RANGE"], id="too-few-followers"),
        pytest.param(
            7, 17, 8, ["ROLE_COUNT_OUT_OF_RANGE", "ROLE_COUNT_OUT_OF_RANGE"], id="both-roles"
        ),
    ],
)
def test_role_count_range(
    n_leaders: int, n_followers: int, n_positions: int, expected: list[str]
) -> None:
    assert codes(team(n_leaders, n_followers, n_positions)) == expected


def test_role_count_message_is_rendered() -> None:
    broken = Team(dancers=roster(2, 3), n_positions=3)
    issue = check_feasibility(broken)[0]
    assert issue.code == "ROLE_COUNT_OUT_OF_RANGE"
    assert "positions" in issue.message
    assert issue.involved_ids == ("led0", "led1")


def test_messages_render_in_the_active_language(german: None) -> None:
    broken = Team(dancers=roster(2, 3), n_positions=3)
    issue = check_feasibility(broken)[0]
    assert "Positionen" in issue.message
    assert "Herren" in issue.message


# -- Startanspruch -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("n_leaders", "n_pole_position", "expected"),
    [
        # 10 Herren over 8 positions => 6 single positions, 2 doubled.
        pytest.param(10, 6, [], id="exactly-as-many-as-single-positions"),
        pytest.param(10, 7, ["TOO_MANY_POLE_POSITION"], id="one-too-many"),
        # 16 Herren over 8 positions => every position doubled, no room at all.
        pytest.param(16, 1, ["TOO_MANY_POLE_POSITION"], id="all-positions-doubled"),
        # 8 Herren over 8 positions => every position single, everyone may have it.
        pytest.param(8, 8, [], id="all-positions-single"),
    ],
)
def test_pole_position_count(n_leaders: int, n_pole_position: int, expected: list[str]) -> None:
    flags = {f"led{i}": {"is_pole_position": True} for i in range(n_pole_position)}
    assert codes(team(n_leaders, 8, 8, **flags)) == expected


def test_pole_position_is_checked_per_role() -> None:
    flags = {f"fol{i}": {"is_pole_position": True} for i in range(7)}
    issues = check_feasibility(team(10, 10, 8, **flags))
    assert [i.code for i in issues] == ["TOO_MANY_POLE_POSITION"]
    assert "Followers" in issues[0].message


# -- Coachingbedarf ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("n_leaders", "n_coaching", "expected"),
    [
        # 10 Herren over 8 positions => 2 doubled positions. Each coaching dancer needs
        # their own doubled position with an experienced partner, so at most 2 fit.
        pytest.param(10, 2, [], id="exactly-as-many-as-doubles"),
        pytest.param(10, 3, ["TOO_MANY_COACHING"], id="one-too-many"),
        # 9 Herren over 8 positions => a single doubled position, seating one coaching dancer.
        pytest.param(9, 1, [], id="one-double-fits-one"),
        pytest.param(9, 2, ["TOO_MANY_COACHING"], id="one-double-overflow"),
        # 8 Herren over 8 positions => no doubled position exists.
        pytest.param(8, 1, ["TOO_MANY_COACHING"], id="no-doubles-at-all"),
    ],
)
def test_coaching_count(n_leaders: int, n_coaching: int, expected: list[str]) -> None:
    flags = {f"led{i}": {"needs_coaching": True} for i in range(n_coaching)}
    assert codes(team(n_leaders, 8, 8, **flags)) == expected


def test_pole_position_and_coaching_are_reported_together() -> None:
    flags: dict[str, dict[str, bool]] = {f"led{i}": {"is_pole_position": True} for i in range(7)}
    flags |= {f"led{i}": {"needs_coaching": True} for i in range(7, 9)}
    # 10 Herren: 6 single positions (7 Startanspruch is one too many) and 2 doubled
    # positions (2 coaching fits), so only the Startanspruch check fires.
    assert codes(team(10, 8, 8, **flags)) == ["TOO_MANY_POLE_POSITION"]


# -- hard vetoes -------------------------------------------------------------------------


def test_veto_pairs_are_symmetric_even_though_preferences_are_not() -> None:
    instance = team(3, 3, 3, not_desired("led0", tier(1, "fol0")))
    assert veto_pairs(instance, SolverConfig()) == {frozenset({"led0", "fol0"})}


def test_veto_pairs_respect_veto_tier() -> None:
    instance = team(3, 3, 3, not_desired("led0", tier(1, "fol0"), tier(2, "fol1")))
    assert veto_pairs(instance, SolverConfig(veto_tier=1)) == {frozenset({"led0", "fol0"})}
    assert veto_pairs(instance, SolverConfig(veto_tier=2)) == {
        frozenset({"led0", "fol0"}),
        frozenset({"led0", "fol1"}),
    }
    assert veto_pairs(instance, SolverConfig(veto_tier=None)) == set()


def test_veto_all_cross_role_is_infeasible() -> None:
    instance = team(3, 3, 3, not_desired("led0", tier(1, "fol0", "fol1", "fol2")))
    issues = check_feasibility(instance)
    assert "VETO_ALL_CROSS_ROLE" in [i.code for i in issues]
    assert issues[0].involved_ids == ("led0",)
    assert "every position" in issues[0].message


def test_veto_all_cross_role_is_not_reported_when_vetoes_are_off() -> None:
    instance = team(3, 3, 3, not_desired("led0", tier(1, "fol0", "fol1", "fol2")))
    assert check_feasibility(instance, SolverConfig(veto_tier=None)) == []


def test_veto_coaching_isolated() -> None:
    # led0 needs coaching but vetoes both other Herren, so no Doppelbesetzung can include them.
    instance = team(
        4,
        4,
        3,
        not_desired("led0", tier(1, "led1", "led2", "led3")),
        **{"led0": {"needs_coaching": True}},
    )
    config = SolverConfig(scope=PreferenceScope.ALL)
    assert "VETO_COACHING_ISOLATED" in codes(instance, config)


def test_veto_coaching_isolated_when_the_only_free_partner_needs_coaching_too() -> None:
    # 5 Herren over 3 positions => 2 doubled. led0 vetoes led2..led4; the only Herr left,
    # led1, needs coaching himself and is no experienced partner, so led0 is isolated.
    instance = team(
        5,
        4,
        3,
        not_desired("led0", tier(1, "led2", "led3", "led4")),
        **{"led0": {"needs_coaching": True}, "led1": {"needs_coaching": True}},
    )
    config = SolverConfig(scope=PreferenceScope.ALL)
    assert "VETO_COACHING_ISOLATED" in codes(instance, config)


def test_same_role_vetoes_are_ignored_under_cross_role_only() -> None:
    instance = team(
        4,
        4,
        3,
        not_desired("led0", tier(1, "led1", "led2", "led3")),
        **{"led0": {"needs_coaching": True}},
    )
    config = SolverConfig(scope=PreferenceScope.CROSS_ROLE_ONLY)
    assert check_feasibility(instance, config) == []


def test_veto_forces_singles() -> None:
    # 4 Herren over 3 positions => 1 doubled, 2 single. If three Herren can pair with
    # nobody, they cannot all sit on the two single positions.
    instance = team(
        4,
        4,
        3,
        not_desired("led0", tier(1, "led1", "led2", "led3")),
        not_desired("led1", tier(1, "led2", "led3")),
        not_desired("led2", tier(1, "led3")),
    )
    assert "VETO_FORCES_SINGLES" in codes(instance, SolverConfig(scope=PreferenceScope.ALL))


def test_role_count_issues_short_circuit_veto_checks() -> None:
    instance = team(2, 3, 3, not_desired("led0", tier(1, "fol0", "fol1", "fol2")))
    # n_single_positions would go negative, so the veto checks must not run at all.
    assert codes(instance) == ["ROLE_COUNT_OUT_OF_RANGE"]


def test_check_feasibility_defaults_to_default_config(small: Team) -> None:
    assert check_feasibility(small, None) == check_feasibility(small)


def test_role_helper_counts(small: Team) -> None:
    assert small.n_doubled_positions(Role.LEADER) == 1
    assert small.n_single_positions(Role.LEADER) == 2


# -- coach constraints (SPEC.md 8, 7.) ------------------------------------------------------


def test_together_components_merge_over_a_shared_member() -> None:
    # {led0, led1} and {led1, fol0} both on one position means all three are; checking the
    # groups as written would miss it.
    instance = with_coach(team(4, 4, 4), together(("led0", "led1"), ("led1", "fol0")))
    assert together_components(instance) == [frozenset({"led0", "led1", "fol0"})]


def test_together_components_of_an_untouched_team_are_empty(small: Team) -> None:
    assert together_components(small) == []


def test_a_clean_coach_rule_passes() -> None:
    instance = with_coach(team(5, 5, 4), together(("led0", "fol0")))
    assert codes(instance) == []
    assert codes(with_coach(team(5, 5, 4), apart(("led0", "led1")))) == []


def test_three_of_one_role_never_fit_on_one_position() -> None:
    instance = with_coach(team(6, 6, 4), together(("led0", "led1", "led2")))
    assert codes(instance) == ["COACH_TOGETHER_TOO_MANY_OF_ROLE"]


def test_more_together_rules_than_doubled_positions() -> None:
    # 5 leaders over 4 positions => exactly one doubled leader position, but two rules each
    # want their own.
    instance = with_coach(team(5, 5, 4), together(("led0", "led1"), ("led2", "led3")))
    assert codes(instance) == ["COACH_TOGETHER_NEEDS_DOUBLES"]


def test_a_pole_position_dancer_cannot_be_forced_to_share() -> None:
    instance = with_coach(
        team(5, 5, 4, **{"led0": {"is_pole_position": True}}), together(("led0", "led1"))
    )
    assert codes(instance) == ["COACH_TOGETHER_POLE_POSITION"]


def test_two_coaching_dancers_cannot_be_forced_together() -> None:
    instance = with_coach(
        team(
            6,
            6,
            4,
            **{"led0": {"needs_coaching": True}, "led1": {"needs_coaching": True}},
        ),
        together(("led0", "led1")),
    )
    assert codes(instance) == ["COACH_TOGETHER_TWO_COACHING"]


def test_a_together_rule_cannot_contradict_a_veto() -> None:
    instance = with_coach(
        team(5, 5, 4, not_desired("led0", tier(1, "fol0"))), together(("led0", "fol0"))
    )
    assert codes(instance) == ["COACH_TOGETHER_VETO"]
    # Without hard vetoes the rule is simply the coach overruling a dislike, which is allowed.
    assert codes(instance, SolverConfig(veto_tier=None)) == []


def test_a_pair_cannot_be_both_together_and_apart() -> None:
    instance = with_coach(
        team(5, 5, 4),
        CoachConstraints(
            together=[frozenset({"led0", "fol0"})], apart=[frozenset({"led0", "fol0"})]
        ),
    )
    assert codes(instance) == ["COACH_TOGETHER_AND_APART"]


def test_an_apart_rule_cannot_outnumber_the_positions() -> None:
    instance = with_coach(team(6, 6, 4), apart(("led0", "led1", "led2", "led3", "led4")))
    assert codes(instance) == ["COACH_APART_TOO_MANY"]


def test_coach_issues_name_the_dancers_involved() -> None:
    issue = check_feasibility(with_coach(team(6, 6, 4), together(("led0", "led1", "led2"))))[0]
    assert issue.involved_ids == ("led0", "led1", "led2")
    assert "LED0" in issue.message


def test_the_role_count_gate_still_comes_first() -> None:
    # A broken roster hides the coach checks: the doubled-position arithmetic they rest on is
    # meaningless until the role counts are in range.
    assert codes(with_coach(team(3, 8, 8), together(("led0", "led1", "led2")))) == [
        "ROLE_COUNT_OUT_OF_RANGE"
    ]
