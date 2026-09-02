"""Derivations shared by the CLI and the UI.

These are the numbers both surfaces show. A disagreement between them would be invisible in a
rendering test, because each surface would still be self-consistent -- so they are asserted
here, once, by value.
"""

from __future__ import annotations

from dancepartner.model import PreferenceScope, Role, SolverConfig
from dancepartner.reporting import (
    MAX_GROUP_SIZE,
    exchange_groups,
    group_numbers,
    moved_dancers,
    positions_by_dancer,
    respected_not_desired,
    satisfaction_ratio,
    satisfaction_rows,
    unfulfilled_desired,
)
from dancepartner.scoring import build_solution
from dancepartner.solver import solve

from .builders import apart, desired, not_desired, team, tier, together, with_coach

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


# -- satisfaction_ratio -------------------------------------------------------------------


def test_satisfaction_ratio_is_one_when_the_top_wish_is_fulfilled() -> None:
    instance = team(3, 3, 3, desired("led0", tier(1, "fol0"), tier(2, "fol1")))
    config = SolverConfig()
    solution = build_solution(
        instance, config, [["led0", "fol0"], ["led1", "fol1"], ["led2", "fol2"]]
    )
    assert satisfaction_ratio(instance, config, "led0", solution.per_dancer["led0"]) == 1.0


def test_satisfaction_ratio_is_below_one_for_a_weaker_fulfilled_tier() -> None:
    instance = team(3, 3, 3, desired("led0", tier(1, "fol0"), tier(2, "fol1")))
    config = SolverConfig()
    solution = build_solution(
        instance, config, [["led0", "fol1"], ["led1", "fol0"], ["led2", "fol2"]]
    )
    # K = 2: the granted tier-2 wish is worth half the tier-1 denominator.
    assert satisfaction_ratio(instance, config, "led0", solution.per_dancer["led0"]) == 0.5


def test_satisfaction_ratio_is_none_for_a_neutral_dancer() -> None:
    instance = team(3, 3, 3, desired("led0", tier(1, "fol0")))
    config = SolverConfig()
    solution = build_solution(
        instance, config, [["led0", "fol0"], ["led1", "fol1"], ["led2", "fol2"]]
    )
    # led1 submitted nothing: neutral, not unhappy.
    assert satisfaction_ratio(instance, config, "led1", solution.per_dancer["led1"]) is None


def test_satisfaction_ratio_is_none_when_every_entry_is_out_of_scope() -> None:
    # A same-role wish under CROSS_ROLE_ONLY is data the model does not use.
    instance = team(3, 3, 3, desired("led0", tier(1, "led1")))
    config = SolverConfig(scope=PreferenceScope.CROSS_ROLE_ONLY)
    solution = build_solution(
        instance, config, [["led0", "fol0"], ["led1", "fol1"], ["led2", "fol2"]]
    )
    assert satisfaction_ratio(instance, config, "led0", solution.per_dancer["led0"]) is None


def test_satisfaction_ratio_of_an_anti_only_survey_starts_at_one() -> None:
    instance = team(3, 3, 3, not_desired("led0", tier(1, "fol0")))
    config = SolverConfig(veto_tier=None)
    respected = build_solution(
        instance, config, [["led0", "fol1"], ["led1", "fol0"], ["led2", "fol2"]]
    )
    violated = build_solution(
        instance, config, [["led0", "fol0"], ["led1", "fol1"], ["led2", "fol2"]]
    )
    assert satisfaction_ratio(instance, config, "led0", respected.per_dancer["led0"]) == 1.0
    # The one violated dislike wipes out the whole baseline: -2 on a denominator of 2.
    assert satisfaction_ratio(instance, config, "led0", violated.per_dancer["led0"]) == 0.0


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


# -- exchange_groups ------------------------------------------------------------------------


def test_exchange_groups_finds_freely_interchangeable_neutrals() -> None:
    # Nobody stated a preference, so any same-role rearrangement is equally good: all three
    # followers form one group, all three leaders another. One solution is enough -- the
    # permutations are verified directly, not looked up in a shortlist.
    instance = team(3, 3, 3)
    config = SolverConfig()
    solution = build_solution(
        instance, config, [["led0", "fol0"], ["led1", "fol1"], ["led2", "fol2"]]
    )
    groups = exchange_groups(solution, instance, config)

    assert [(g.number, g.role, g.dancer_ids) for g in groups] == [
        (1, Role.FOLLOWER, ["fol0", "fol1", "fol2"]),
        (2, Role.LEADER, ["led0", "led1", "led2"]),
    ]
    assert groups[0].labels == {"fol0": "A", "fol1": "B", "fol2": "C"}
    assert group_numbers(groups) == {
        "fol0": 1,
        "fol1": 1,
        "fol2": 1,
        "led0": 2,
        "led1": 2,
        "led2": 2,
    }


def test_exchange_groups_exclude_a_dancer_whose_swap_costs_a_wish() -> None:
    # Moving fol0 (or led0) away from the fulfilled tier-1 wish changes the score vector, so
    # neither is interchangeable; the unnamed rest still is.
    instance = team(3, 3, 3, desired("led0", tier(1, "fol0")))
    config = SolverConfig()
    solution = build_solution(
        instance, config, [["led0", "fol0"], ["led1", "fol1"], ["led2", "fol2"]]
    )
    groups = exchange_groups(solution, instance, config)

    assert [(g.role, g.dancer_ids) for g in groups] == [
        (Role.FOLLOWER, ["fol1", "fol2"]),
        (Role.LEADER, ["led1", "led2"]),
    ]


def test_exchange_groups_respect_vetoes() -> None:
    # fol1 must never stand with led2, so any arrangement sending fol1 to C is out; the
    # greedy build keeps {fol0, fol1} and leaves fol2 alone. The same veto blocks led2 from
    # position B, splitting the leaders analogously.
    instance = team(3, 3, 3, not_desired("fol1", tier(1, "led2")))
    config = SolverConfig()
    solution = build_solution(
        instance, config, [["led0", "fol0"], ["led1", "fol1"], ["led2", "fol2"]]
    )
    groups = exchange_groups(solution, instance, config)

    assert [(g.role, g.dancer_ids) for g in groups] == [
        (Role.FOLLOWER, ["fol0", "fol1"]),
        (Role.LEADER, ["led0", "led1"]),
    ]


def test_exchange_groups_respect_a_coach_rule_to_stay_apart() -> None:
    # The coach keeps fol1 and led2 apart. Exactly the veto case above, but set by the coach
    # rather than derived from the survey -- the swaps it forbids are the same ones.
    instance = with_coach(team(3, 3, 3), apart(("fol1", "led2")))
    config = SolverConfig()
    solution = build_solution(
        instance, config, [["led0", "fol0"], ["led1", "fol1"], ["led2", "fol2"]]
    )
    groups = exchange_groups(solution, instance, config)

    assert [(g.role, g.dancer_ids) for g in groups] == [
        (Role.FOLLOWER, ["fol0", "fol1"]),
        (Role.LEADER, ["led0", "led1"]),
    ]


def test_exchange_groups_respect_a_coach_rule_to_stay_together() -> None:
    # led0 and fol0 must share a position, so no swap may move either of them off B -- a
    # "free" rotation that split the pair would break the coach's own rule.
    instance = with_coach(team(3, 3, 3), together(("led0", "fol0")))
    config = SolverConfig()
    solution = build_solution(
        instance, config, [["led1", "fol1"], ["led0", "fol0"], ["led2", "fol2"]]
    )
    groups = exchange_groups(solution, instance, config)

    assert [(g.role, g.dancer_ids) for g in groups] == [
        (Role.FOLLOWER, ["fol1", "fol2"]),
        (Role.LEADER, ["led1", "led2"]),
    ]
    assert "led0" not in group_numbers(groups)
    assert "fol0" not in group_numbers(groups)


def test_exchange_groups_respect_the_coaching_pairing() -> None:
    # led0 needs coaching: any arrangement leaving him alone is invalid, so he stays put
    # while the three experienced leaders rotate freely. His co-positioned partner led1 is
    # never grouped with him -- swapping two dancers on one position changes nothing.
    instance = team(4, 3, 3, **{"led0": {"needs_coaching": True}})
    config = SolverConfig()
    solution = build_solution(
        instance, config, [["led0", "led1", "fol0"], ["led2", "fol1"], ["led3", "fol2"]]
    )
    groups = exchange_groups(solution, instance, config)

    assert [(g.role, g.dancer_ids) for g in groups] == [
        (Role.FOLLOWER, ["fol0", "fol1", "fol2"]),
        (Role.LEADER, ["led1", "led2", "led3"]),
    ]
    assert "led0" not in group_numbers(groups)


def test_exchange_groups_never_pair_two_coaching_dancers() -> None:
    # fol0's wish pins led0 (coaching) on A. Swapping led1 for led2 would double up the two
    # coaching dancers on A -- invalid, so led1 and led2 land in different groups.
    instance = team(
        6,
        4,
        3,
        desired("fol0", tier(1, "led0")),
        **{"led0": {"needs_coaching": True}, "led2": {"needs_coaching": True}},
    )
    config = SolverConfig()
    solution = build_solution(
        instance,
        config,
        [["led0", "led1", "fol0"], ["led2", "led3", "fol1"], ["led4", "led5", "fol2", "fol3"]],
    )
    groups = exchange_groups(solution, instance, config)
    numbers = group_numbers(groups)

    assert "led0" not in numbers
    assert "led1" in numbers
    assert "led2" in numbers
    assert numbers["led1"] != numbers["led2"]


def test_exchange_groups_respect_a_pole_position() -> None:
    # led2 holds a pole position: he may swap onto another single slot but never onto the
    # doubled position A, and nobody may double up with him.
    instance = team(4, 3, 3, **{"led2": {"is_pole_position": True}})
    config = SolverConfig()
    solution = build_solution(
        instance, config, [["led0", "led1", "fol0"], ["led2", "fol1"], ["led3", "fol2"]]
    )
    groups = exchange_groups(solution, instance, config)

    leaders = next(g for g in groups if g.role is Role.LEADER)
    assert leaders.dancer_ids == ["led0", "led3"]
    assert "led2" not in group_numbers(groups)


def test_exchange_groups_verify_full_permutation_closure() -> None:
    # Every pairwise swap of fol0/fol1/fol2 preserves the score vector, but the three-cycles
    # do not -- the wish matrix is built so the tier-1 and tier-2 fulfilments only balance
    # pairwise. A transitive chain would claim a group of three; the closure check must not.
    instance = team(
        4,
        4,
        4,
        desired("led0", tier(1, "fol3"), tier(2, "fol0", "fol1", "fol2")),
        desired("led1", tier(1, "fol0", "fol1"), tier(2, "fol2")),
        desired("led2", tier(1, "fol1"), tier(2, "fol0", "fol2")),
    )
    config = SolverConfig()
    solution = build_solution(
        instance,
        config,
        [["led0", "fol0"], ["led1", "fol1"], ["led2", "fol2"], ["led3", "fol3"]],
    )
    groups = exchange_groups(solution, instance, config)

    assert [(g.role, g.dancer_ids) for g in groups] == [
        (Role.FOLLOWER, ["fol0", "fol1"]),
        (Role.LEADER, ["led0", "led1"]),
    ]
    assert "fol2" not in group_numbers(groups)


def test_exchange_groups_cap_the_group_size() -> None:
    # Nine neutral followers on eight positions: at most MAX_GROUP_SIZE join one group, and
    # the second follower of the doubled position is skipped (same position, nothing to swap).
    instance = team(9, 9, 8)
    config = SolverConfig()
    positions = [[f"led{i}", f"fol{i}"] for i in range(7)]
    positions.append(["led7", "led8", "fol7", "fol8"])
    solution = build_solution(instance, config, positions)
    groups = exchange_groups(solution, instance, config)

    followers = next(g for g in groups if g.role is Role.FOLLOWER)
    assert len(followers.dancer_ids) == MAX_GROUP_SIZE
    assert len({followers.labels[i] for i in followers.dancer_ids}) == MAX_GROUP_SIZE
