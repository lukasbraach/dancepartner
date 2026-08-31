"""Counting pre-checks, including the exact boundary cases."""

from __future__ import annotations

import pytest

from dancepartner.feasibility import check_feasibility, veto_pairs
from dancepartner.model import PreferenceScope, Role, SolverConfig, Team

from .builders import nicht_wunsch, roster, team, tier


def codes(team_: Team, config: SolverConfig | None = None) -> list[str]:
    return [issue.code for issue in check_feasibility(team_, config)]


def test_clean_instance_has_no_issues(small: Team) -> None:
    assert check_feasibility(small) == []


# -- role counts -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("n_herren", "n_damen", "n_positions", "expected"),
    [
        pytest.param(8, 8, 8, [], id="n=P-lower-boundary"),
        pytest.param(16, 16, 8, [], id="n=2P-upper-boundary"),
        pytest.param(7, 8, 8, ["ROLE_COUNT_OUT_OF_RANGE"], id="too-few-herren"),
        pytest.param(17, 8, 8, ["ROLE_COUNT_OUT_OF_RANGE"], id="too-many-herren"),
        pytest.param(8, 7, 8, ["ROLE_COUNT_OUT_OF_RANGE"], id="too-few-damen"),
        pytest.param(
            7, 17, 8, ["ROLE_COUNT_OUT_OF_RANGE", "ROLE_COUNT_OUT_OF_RANGE"], id="both-roles"
        ),
    ],
)
def test_role_count_range(
    n_herren: int, n_damen: int, n_positions: int, expected: list[str]
) -> None:
    assert codes(team(n_herren, n_damen, n_positions)) == expected


def test_role_count_message_is_german() -> None:
    broken = Team(dancers=roster(2, 3), n_positions=3)
    issue = check_feasibility(broken)[0]
    assert issue.code == "ROLE_COUNT_OUT_OF_RANGE"
    assert "Positionen" in issue.message_de
    assert issue.involved_ids == ("h0", "h1")


# -- Startanspruch -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("n_herren", "n_startanspruch", "expected"),
    [
        # 10 Herren over 8 positions => 6 single positions, 2 doubled.
        pytest.param(10, 6, [], id="exactly-as-many-as-single-positions"),
        pytest.param(10, 7, ["TOO_MANY_STARTANSPRUCH"], id="one-too-many"),
        # 16 Herren over 8 positions => every position doubled, no room at all.
        pytest.param(16, 1, ["TOO_MANY_STARTANSPRUCH"], id="all-positions-doubled"),
        # 8 Herren over 8 positions => every position single, everyone may have it.
        pytest.param(8, 8, [], id="all-positions-single"),
    ],
)
def test_startanspruch_count(n_herren: int, n_startanspruch: int, expected: list[str]) -> None:
    flags = {f"h{i}": {"has_startanspruch": True} for i in range(n_startanspruch)}
    assert codes(team(n_herren, 8, 8, **flags)) == expected


def test_startanspruch_is_checked_per_role() -> None:
    flags = {f"d{i}": {"has_startanspruch": True} for i in range(7)}
    issues = check_feasibility(team(10, 10, 8, **flags))
    assert [i.code for i in issues] == ["TOO_MANY_STARTANSPRUCH"]
    assert "Damen" in issues[0].message_de


# -- Coachingbedarf ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("n_herren", "n_coaching", "expected"),
    [
        # 10 Herren over 8 positions => 2 doubled positions, seating 4 coaching dancers.
        pytest.param(10, 4, [], id="even-exactly-full"),
        pytest.param(10, 3, [], id="odd-fits"),
        pytest.param(10, 5, ["TOO_MANY_COACHING"], id="odd-one-too-many"),
        pytest.param(10, 6, ["TOO_MANY_COACHING"], id="even-two-too-many"),
        # 9 Herren over 8 positions => a single doubled position, seating 2.
        pytest.param(9, 2, [], id="one-double-even"),
        pytest.param(9, 3, ["TOO_MANY_COACHING"], id="one-double-odd-overflow"),
        # 8 Herren over 8 positions => no doubled position exists.
        pytest.param(8, 1, ["TOO_MANY_COACHING"], id="no-doubles-at-all"),
    ],
)
def test_coaching_count(n_herren: int, n_coaching: int, expected: list[str]) -> None:
    flags = {f"h{i}": {"needs_coaching": True} for i in range(n_coaching)}
    assert codes(team(n_herren, 8, 8, **flags)) == expected


def test_startanspruch_and_coaching_are_reported_together() -> None:
    flags: dict[str, dict[str, bool]] = {f"h{i}": {"has_startanspruch": True} for i in range(7)}
    flags |= {f"h{i}": {"needs_coaching": True} for i in range(7, 10)}
    # 10 Herren: 6 single positions (7 Startanspruch is one too many) and 2 doubled
    # positions seating 4 (3 coaching fits), so only the Startanspruch check fires.
    assert codes(team(10, 8, 8, **flags)) == ["TOO_MANY_STARTANSPRUCH"]


# -- hard vetoes -------------------------------------------------------------------------


def test_veto_pairs_are_symmetric_even_though_preferences_are_not() -> None:
    instance = team(3, 3, 3, nicht_wunsch("h0", tier(1, "d0")))
    assert veto_pairs(instance, SolverConfig()) == {frozenset({"h0", "d0"})}


def test_veto_pairs_respect_veto_tier() -> None:
    instance = team(3, 3, 3, nicht_wunsch("h0", tier(1, "d0"), tier(2, "d1")))
    assert veto_pairs(instance, SolverConfig(veto_tier=1)) == {frozenset({"h0", "d0"})}
    assert veto_pairs(instance, SolverConfig(veto_tier=2)) == {
        frozenset({"h0", "d0"}),
        frozenset({"h0", "d1"}),
    }
    assert veto_pairs(instance, SolverConfig(veto_tier=None)) == set()


def test_veto_all_cross_role_is_infeasible() -> None:
    instance = team(3, 3, 3, nicht_wunsch("h0", tier(1, "d0", "d1", "d2")))
    issues = check_feasibility(instance)
    assert "VETO_ALL_CROSS_ROLE" in [i.code for i in issues]
    assert issues[0].involved_ids == ("h0",)
    assert "jede Position" in issues[0].message_de


def test_veto_all_cross_role_is_not_reported_when_vetoes_are_off() -> None:
    instance = team(3, 3, 3, nicht_wunsch("h0", tier(1, "d0", "d1", "d2")))
    assert check_feasibility(instance, SolverConfig(veto_tier=None)) == []


def test_veto_coaching_isolated() -> None:
    # h0 needs coaching but vetoes both other Herren, so no Doppelbesetzung can include them.
    instance = team(
        4,
        4,
        3,
        nicht_wunsch("h0", tier(1, "h1", "h2", "h3")),
        **{"h0": {"needs_coaching": True}},
    )
    config = SolverConfig(scope=PreferenceScope.ALL)
    assert "VETO_COACHING_ISOLATED" in codes(instance, config)


def test_same_role_vetoes_are_ignored_under_cross_role_only() -> None:
    instance = team(
        4,
        4,
        3,
        nicht_wunsch("h0", tier(1, "h1", "h2", "h3")),
        **{"h0": {"needs_coaching": True}},
    )
    assert check_feasibility(instance, SolverConfig()) == []


def test_veto_forces_singles() -> None:
    # 4 Herren over 3 positions => 1 doubled, 2 single. If three Herren can pair with
    # nobody, they cannot all sit on the two single positions.
    instance = team(
        4,
        4,
        3,
        nicht_wunsch("h0", tier(1, "h1", "h2", "h3")),
        nicht_wunsch("h1", tier(1, "h2", "h3")),
        nicht_wunsch("h2", tier(1, "h3")),
    )
    assert "VETO_FORCES_SINGLES" in codes(instance, SolverConfig(scope=PreferenceScope.ALL))


def test_role_count_issues_short_circuit_veto_checks() -> None:
    instance = team(2, 3, 3, nicht_wunsch("h0", tier(1, "d0", "d1", "d2")))
    # n_single_positions would go negative, so the veto checks must not run at all.
    assert codes(instance) == ["ROLE_COUNT_OUT_OF_RANGE"]


def test_check_feasibility_defaults_to_default_config(small: Team) -> None:
    assert check_feasibility(small, None) == check_feasibility(small)


def test_role_helper_counts(small: Team) -> None:
    assert small.n_doubled_positions(Role.HERR) == 1
    assert small.n_single_positions(Role.HERR) == 2
