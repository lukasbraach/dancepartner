"""Derivations shared by the CLI and the UI.

These are the numbers both surfaces show. A disagreement between them would be invisible in a
rendering test, because each surface would still be self-consistent -- so they are asserted
here, once, by value.
"""

from __future__ import annotations

from dancepartner.model import PreferenceScope, SolverConfig
from dancepartner.reporting import (
    moved_dancers,
    positions_by_dancer,
    respected_not_desired,
    satisfaction_rows,
    unfulfilled_desired,
)
from dancepartner.scoring import build_solution
from dancepartner.solver import solve

from .builders import desired, not_desired, team, tier

# -- positions_by_dancer ------------------------------------------------------------------


def test_positions_by_dancer_covers_every_dancer_exactly_once() -> None:
    instance = team(3, 3, 3)
    solution = build_solution(
        instance, SolverConfig(), [["led0", "fol0"], ["led1", "fol1"], ["led2", "fol2"]]
    )
    assert positions_by_dancer(solution) == {
        "led0": "A",
        "fol0": "A",
        "led1": "B",
        "fol1": "B",
        "led2": "C",
        "fol2": "C",
    }


# -- satisfaction_rows --------------------------------------------------------------------


def test_satisfaction_rows_puts_the_unhappiest_dancer_first() -> None:
    instance = team(3, 3, 3, desired("led0", tier(1, "fol0")))
    solution = build_solution(
        instance, SolverConfig(), [["led0", "fol0"], ["led1", "fol1"], ["led2", "fol2"]]
    )
    rows = satisfaction_rows(solution, instance)

    scores = [sat.score for _, _, sat in rows]
    assert scores == sorted(scores), "rows must ascend by score"
    # led0 is the only dancer with a granted wish, so it sorts last.
    assert rows[-1][0] == "led0"
    assert rows[-1][2].score > 0


def test_satisfaction_rows_breaks_ties_by_id_and_carries_the_display_name() -> None:
    instance = team(3, 3, 3)
    solution = build_solution(
        instance, SolverConfig(), [["led0", "fol0"], ["led1", "fol1"], ["led2", "fol2"]]
    )
    rows = satisfaction_rows(solution, instance)

    assert [dancer_id for dancer_id, _, _ in rows] == sorted(instance.dancers_by_id)
    assert all(name == dancer_id.upper() for dancer_id, name, _ in rows)


# -- unfulfilled_desired ------------------------------------------------------------------


def test_unfulfilled_desired_lists_only_the_wishes_that_were_missed() -> None:
    instance = team(3, 3, 3, desired("led0", tier(1, "fol0", "fol1")))
    solution = build_solution(
        instance, SolverConfig(), [["led0", "fol0"], ["led1", "fol1"], ["led2", "fol2"]]
    )
    satisfaction = solution.per_dancer["led0"]

    assert satisfaction.fulfilled_desired == {1: ["fol0"]}
    assert unfulfilled_desired(instance, "led0", satisfaction) == {1: ["fol1"]}


def test_unfulfilled_desired_drops_a_tier_that_was_granted_whole() -> None:
    instance = team(3, 3, 3, desired("led0", tier(1, "fol0")))
    solution = build_solution(
        instance, SolverConfig(), [["led0", "fol0"], ["led1", "fol1"], ["led2", "fol2"]]
    )
    assert unfulfilled_desired(instance, "led0", solution.per_dancer["led0"]) == {}


def test_unfulfilled_desired_is_empty_without_a_survey() -> None:
    instance = team(3, 3, 3)
    solution = build_solution(
        instance, SolverConfig(), [["led0", "fol0"], ["led1", "fol1"], ["led2", "fol2"]]
    )
    assert unfulfilled_desired(instance, "led0", solution.per_dancer["led0"]) == {}


def test_unfulfilled_desired_reports_an_out_of_scope_wish_the_objective_never_scored() -> None:
    # led0 wishing for led1 is same-role, so CROSS_ROLE_ONLY never scores it -- but the coach
    # wrote it down, and a missed wish stays visibly missed.
    instance = team(3, 3, 3, desired("led0", tier(1, "led1")))
    config = SolverConfig(scope=PreferenceScope.CROSS_ROLE_ONLY)
    solution = build_solution(
        instance, config, [["led0", "fol0"], ["led1", "fol1"], ["led2", "fol2"]]
    )
    assert unfulfilled_desired(instance, "led0", solution.per_dancer["led0"]) == {1: ["led1"]}


# -- respected_not_desired ----------------------------------------------------------------


def test_respected_not_desired_credits_only_the_dislikes_actually_avoided() -> None:
    instance = team(3, 3, 3, not_desired("led0", tier(1, "fol0", "fol1")))
    config = SolverConfig(veto_tier=None)
    solution = build_solution(
        instance, config, [["led0", "fol0"], ["led1", "fol1"], ["led2", "fol2"]]
    )
    satisfaction = solution.per_dancer["led0"]

    assert satisfaction.violated_not_desired == {1: ["fol0"]}
    assert respected_not_desired(instance, config, "led0", satisfaction) == {1: ["fol1"]}


def test_respected_not_desired_ignores_pairs_outside_the_scope() -> None:
    # Nothing kept the two leaders apart under CROSS_ROLE_ONLY, so claiming credit for it
    # would be claiming credit for a constraint that does not exist.
    instance = team(3, 3, 3, not_desired("led0", tier(1, "led1")))
    config = SolverConfig(scope=PreferenceScope.CROSS_ROLE_ONLY, veto_tier=None)
    solution = build_solution(
        instance, config, [["led0", "fol0"], ["led1", "fol1"], ["led2", "fol2"]]
    )
    assert respected_not_desired(instance, config, "led0", solution.per_dancer["led0"]) == {}

    wide = SolverConfig(scope=PreferenceScope.ALL, veto_tier=None)
    solution = build_solution(
        instance, wide, [["led0", "fol0"], ["led1", "fol1"], ["led2", "fol2"]]
    )
    assert respected_not_desired(instance, wide, "led0", solution.per_dancer["led0"]) == {
        1: ["led1"]
    }


def test_respected_not_desired_is_empty_without_a_survey() -> None:
    instance = team(3, 3, 3)
    config = SolverConfig()
    solution = build_solution(
        instance, config, [["led0", "fol0"], ["led1", "fol1"], ["led2", "fol2"]]
    )
    assert respected_not_desired(instance, config, "led0", solution.per_dancer["led0"]) == {}


# -- moved_dancers ------------------------------------------------------------------------


def test_moved_dancers_is_empty_against_itself() -> None:
    instance = team(3, 3, 3)
    solution = build_solution(
        instance, SolverConfig(), [["led0", "fol0"], ["led1", "fol1"], ["led2", "fol2"]]
    )
    assert moved_dancers(solution, solution, instance) == []


def test_moved_dancers_names_both_labels_and_sorts_by_name() -> None:
    instance = team(3, 3, 3)
    config = SolverConfig()
    reference = build_solution(
        instance, config, [["led0", "fol0"], ["led1", "fol1"], ["led2", "fol2"]]
    )
    swapped = build_solution(
        instance, config, [["led0", "fol1"], ["led1", "fol0"], ["led2", "fol2"]]
    )
    moved = moved_dancers(reference, swapped, instance)

    assert moved == [("FOL0", "A", "B"), ("FOL1", "B", "A")]
    assert [name for name, _, _ in moved] == sorted(name for name, _, _ in moved)


def test_moved_dancers_is_never_empty_for_two_shortlist_entries() -> None:
    # The shortlist is deduplicated by signature, so distinct entries always differ in who
    # sits with whom -- never merely in which label a group carries.
    instance = team(3, 3, 3, desired("led0", tier(1, "fol0")))
    result = solve(instance, SolverConfig(max_solutions=5))
    assert len(result.solutions) > 1
    for other in result.solutions[1:]:
        assert moved_dancers(result.best, other, instance) != []
