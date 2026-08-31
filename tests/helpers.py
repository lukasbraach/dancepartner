"""Independent verification of a returned solution against every hard constraint.

The solver must never be trusted to have modelled what we think it modelled, so nothing in
here reads the CP-SAT model: it re-derives everything from the ``Solution`` and the ``Team``.
"""

from __future__ import annotations

from dancepartner.feasibility import veto_pairs
from dancepartner.model import Role, SolverConfig, Team
from dancepartner.scoring import Solution, build_satisfaction
from dancepartner.solver import SolveResult


def assert_result_valid(
    result: SolveResult, team: Team, config: SolverConfig | None = None
) -> None:
    """Check the solution *and* that the model's own objective agrees with it.

    ``assert_valid`` alone cannot catch a mis-modelled objective: the scores it compares
    against are recomputed from the assignment by ``scoring``, so they stay correct even when
    the CP-SAT model optimised something else entirely. The stage values are the only window
    onto what the solver actually believed it was maximising, and a broken reification shows
    up here and nowhere else.
    """
    config = config or SolverConfig()
    assert_valid(result.best, team, config)

    expected: dict[str, int] = {
        "maximin": result.best.min_score,
        "sum": result.best.total_score,
        "coupled": sum(
            1
            for position in result.best.positions
            if (len(position.herren) == 2) != (len(position.damen) == 2)
        ),
    }
    for stage in result.stages:
        assert stage.value == expected[stage.name], (
            f"stage {stage.name!r} reports {stage.value} but the assignment gives "
            f"{expected[stage.name]} -- the model is not optimising what it claims to"
        )


def assert_valid(solution: Solution, team: Team, config: SolverConfig | None = None) -> None:
    """Re-check every hard constraint from SPEC.md 8 plus the reported scores."""
    config = config or SolverConfig()
    by_id = team.dancers_by_id

    assert len(solution.positions) == team.n_positions
    assert [position.label for position in solution.positions] == team.labels

    # 1. Every dancer on exactly one position.
    placed = [i for position in solution.positions for i in (*position.herren, *position.damen)]
    assert sorted(placed) == sorted(by_id), f"dancers placed {sorted(placed)}"

    for position in solution.positions:
        # Roles are not mixed up.
        assert all(by_id[i].role is Role.HERR for i in position.herren)
        assert all(by_id[i].role is Role.DAME for i in position.damen)
        # 2. One or two dancers per role per position.
        for role in Role:
            count = len(position.role_ids(role))
            assert 1 <= count <= 2, f"position {position.label}: {count} {role.value}"

        for role in Role:
            for dancer_id in position.role_ids(role):
                dancer = by_id[dancer_id]
                count = len(position.role_ids(role))
                # 3. Startanspruch: alone in their own role.
                if dancer.has_startanspruch:
                    assert count == 1, f"{dancer_id} has Startanspruch but shares with {count - 1}"
                # 4. Coachingbedarf: not alone in their own role.
                if dancer.needs_coaching:
                    assert count == 2, f"{dancer_id} needs coaching but is alone in their role"

    # 5. No vetoed pair shares a position.
    for pair in veto_pairs(team, config):
        for position in solution.positions:
            here = {*position.herren, *position.damen}
            assert not pair <= here, f"vetoed pair {sorted(pair)} on position {position.label}"

    assert_scores_consistent(solution, team, config)


def assert_scores_consistent(
    solution: Solution, team: Team, config: SolverConfig | None = None
) -> None:
    """The reported scores must match an independent recomputation."""
    config = config or SolverConfig()
    groups = [[*position.herren, *position.damen] for position in solution.positions]
    expected = build_satisfaction(team, config, groups)
    assert solution.per_dancer == expected
    assert solution.total_score == sum(s.score for s in expected.values())
    assert solution.min_score == min(s.score for s in expected.values())


def groups_of(solution: Solution) -> list[set[str]]:
    """The dancer id sets per position, for asserting on the shape of an assignment."""
    return [{*position.herren, *position.damen} for position in solution.positions]


def position_of(solution: Solution, dancer_id: str) -> str:
    """The label of the position a dancer ended up on."""
    for position in solution.positions:
        if dancer_id in position.herren or dancer_id in position.damen:
            return position.label
    raise AssertionError(f"{dancer_id} is not on any position")


def share_position(solution: Solution, *dancer_ids: str) -> bool:
    """Whether all the given dancers ended up on the same position."""
    return len({position_of(solution, i) for i in dancer_ids}) == 1
