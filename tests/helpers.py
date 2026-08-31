"""Independent verification of a returned solution against every hard constraint.

The solver must never be trusted to have modelled what we think it modelled, so nothing in
here reads the CP-SAT model: it re-derives everything from the ``Solution`` and the ``Team``.
"""

from __future__ import annotations

from collections import Counter

from dancepartner.feasibility import veto_pairs
from dancepartner.model import Objective, Role, SolverConfig, Team
from dancepartner.scoring import Solution, build_satisfaction
from dancepartner.solver import Sense, SolveResult


def assert_result_valid(
    result: SolveResult, team: Team, config: SolverConfig | None = None
) -> None:
    """Check every returned solution *and* that the model's own objective agrees with them.

    ``assert_valid`` alone cannot catch a mis-modelled objective: the scores it compares
    against are recomputed from the assignment by ``scoring``, so they stay correct even when
    the CP-SAT model optimised something else entirely. The stage values are the only window
    onto what the solver actually believed it was maximising, and a broken reification shows
    up here and nowhere else.
    """
    config = config or SolverConfig()
    for solution in result.solutions:
        assert_valid(solution, team, config)
    assert_shortlist_distinct(result)
    assert_stages_consistent(result, team, config)
    if config.objective is Objective.LEXIMIN:
        assert_leximin_vector(result)


def assert_shortlist_distinct(result: SolveResult) -> None:
    """No two entries of the shortlist may be the same Verpartnerung.

    The signature ignores position labels on purpose (SPEC.md 8): two assignments that differ
    only in which label a group carries are one solution, not two.
    """
    signatures = [solution.signature for solution in result.solutions]
    assert len(set(signatures)) == len(signatures), "the shortlist contains a duplicate"


def stage_expectation(name: str, solution: Solution) -> int:
    """Recompute one stage's value from a concrete solution, independently of the model."""
    if name == "maximin":
        return solution.min_score
    if name == "sum":
        return solution.total_score
    if name == "coupled":
        return sum(
            1
            for position in solution.positions
            if (len(position.leaders) == 2) != (len(position.followers) == 2)
        )
    direction, _, tier = name.partition(".tier")
    if tier:
        rank = int(tier)
        field = "fulfilled_desired" if direction == "desired" else "violated_not_desired"
        return sum(
            len(getattr(satisfaction, field).get(rank, []))
            for satisfaction in solution.per_dancer.values()
        )
    raise AssertionError(f"no independent expectation defined for stage {name!r}")


def assert_stages_consistent(result: SolveResult, team: Team, config: SolverConfig) -> None:
    """Every stage value must match what the best solution actually delivers.

    A later stage can only ever walk an earlier stage's optimum back by that stage's declared
    slack -- ``tier_slack`` for a LEXICOGRAPHIC_TIERS stage, plus whatever
    ``near_optimal_ratio`` allows the enumeration pass to give up. Anything beyond that means
    the model is not optimising what it reports. The slack is recomputed here rather than read
    off the solver, so a bug in the solver's own arithmetic cannot hide behind it.
    """
    del team
    for stage in result.stages:
        if stage.name.startswith("leximin."):
            continue  # covered by assert_leximin_vector
        actual = stage_expectation(stage.name, result.best)
        if stage.locked_at is not None:
            # A later stage walked this one back and the solver then locked in a floor. The
            # assignment must honour that floor -- doing *better* than it is always allowed.
            band = _ratio_slack(stage.locked_at, config.near_optimal_ratio)
            guaranteed = (
                actual >= stage.locked_at - band
                if stage.sense is Sense.MAXIMIZE
                else actual <= stage.locked_at + band
            )
            assert guaranteed, (
                f"stage {stage.name!r} was locked at {stage.locked_at} but the assignment "
                f"gives {actual}"
            )
        allowed = _ratio_slack(stage.value, config.near_optimal_ratio)
        if ".tier" in stage.name:
            allowed += config.tier_slack
        low, high = (
            (stage.value - allowed, stage.value)
            if stage.sense is Sense.MAXIMIZE
            else (stage.value, stage.value + allowed)
        )
        assert low <= actual <= high, (
            f"stage {stage.name!r} reports {stage.value} (slack {allowed}) but the assignment "
            f"gives {actual} -- the model is not optimising what it claims to"
        )


def _ratio_slack(value: int, ratio: float) -> int:
    """How far the enumeration pass may fall short of a stage optimum."""
    return 0 if ratio >= 1.0 else int((1.0 - ratio) * abs(value))


def assert_leximin_vector(result: SolveResult) -> None:
    """The leximin rounds must reconstruct the actual score multiset exactly.

    Round *r* reports a floor and how many dancers got strictly above it, so the number stuck
    at that floor is ``active_before - count``. Replaying that gives the whole sorted score
    vector without looking at the model -- if the rounds and the assignment disagree, one of
    them is lying.
    """
    rounds = [stage for stage in result.stages if stage.name.startswith("leximin.")]
    assert rounds, "a LEXIMIN solve must report leximin stages"
    assert len(rounds) % 2 == 0, "every round is a floor stage plus a count stage"

    active = len(result.best.per_dancer)
    reconstructed: Counter[int] = Counter()
    for index in range(0, len(rounds), 2):
        floor_stage, count_stage = rounds[index], rounds[index + 1]
        assert floor_stage.name.endswith(".floor")
        assert count_stage.name.endswith(".count")
        reconstructed[floor_stage.value] += active - count_stage.value
        active = count_stage.value
    assert active == 0, "the last round must leave nobody above its floor"

    actual = Counter(s.score for s in result.best.per_dancer.values())
    assert reconstructed == actual, (
        f"leximin rounds imply {sorted(reconstructed.elements())} but the assignment gives "
        f"{sorted(actual.elements())}"
    )


def assert_valid(solution: Solution, team: Team, config: SolverConfig | None = None) -> None:
    """Re-check every hard constraint from SPEC.md 8 plus the reported scores."""
    config = config or SolverConfig()
    by_id = team.dancers_by_id

    assert len(solution.positions) == team.n_positions
    assert [position.label for position in solution.positions] == team.labels

    # 1. Every dancer on exactly one position.
    placed = [
        i for position in solution.positions for i in (*position.leaders, *position.followers)
    ]
    assert sorted(placed) == sorted(by_id), f"dancers placed {sorted(placed)}"

    for position in solution.positions:
        # Roles are not mixed up.
        assert all(by_id[i].role is Role.LEADER for i in position.leaders)
        assert all(by_id[i].role is Role.FOLLOWER for i in position.followers)
        # 2. One or two dancers per role per position.
        for role in Role:
            count = len(position.role_ids(role))
            assert 1 <= count <= 2, f"position {position.label}: {count} {role.value}"

        for role in Role:
            for dancer_id in position.role_ids(role):
                dancer = by_id[dancer_id]
                count = len(position.role_ids(role))
                # 3. Startanspruch: alone in their own role.
                if dancer.is_pole_position:
                    assert count == 1, f"{dancer_id} has Startanspruch but shares with {count - 1}"
                # 4. Coachingbedarf: not alone in their own role.
                if dancer.needs_coaching:
                    assert count == 2, f"{dancer_id} needs coaching but is alone in their role"

            # 5. At most one coaching dancer per role per position.
            coaching_here = [i for i in position.role_ids(role) if by_id[i].needs_coaching]
            assert len(coaching_here) <= 1, (
                f"position {position.label}: {coaching_here} all need coaching"
            )

    # 6. No vetoed pair shares a position.
    for pair in veto_pairs(team, config):
        for position in solution.positions:
            here = {*position.leaders, *position.followers}
            assert not pair <= here, f"vetoed pair {sorted(pair)} on position {position.label}"

    assert_scores_consistent(solution, team, config)


def assert_scores_consistent(
    solution: Solution, team: Team, config: SolverConfig | None = None
) -> None:
    """The reported scores must match an independent recomputation."""
    config = config or SolverConfig()
    groups = [[*position.leaders, *position.followers] for position in solution.positions]
    expected = build_satisfaction(team, config, groups)
    assert solution.per_dancer == expected
    assert solution.total_score == sum(s.score for s in expected.values())
    assert solution.min_score == min(s.score for s in expected.values())


def groups_of(solution: Solution) -> list[set[str]]:
    """The dancer id sets per position, for asserting on the shape of an assignment."""
    return [{*position.leaders, *position.followers} for position in solution.positions]


def position_of(solution: Solution, dancer_id: str) -> str:
    """The label of the position a dancer ended up on."""
    for position in solution.positions:
        if dancer_id in position.leaders or dancer_id in position.followers:
            return position.label
    raise AssertionError(f"{dancer_id} is not on any position")


def share_position(solution: Solution, *dancer_ids: str) -> bool:
    """Whether all the given dancers ended up on the same position."""
    return len({position_of(solution, i) for i in dancer_ids}) == 1
