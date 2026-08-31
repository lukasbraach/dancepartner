"""Symmetry breaking must not change the optimum, only the work needed to prove it.

Positions are unordered, so the 8! = 40320 relabellings of any assignment are all equally
good. The canonical numbering removes them from the search space.
"""

from __future__ import annotations

from dancepartner.model import Role, SolverConfig, Team
from dancepartner.solver import solve

from .builders import desired, not_desired, roster, tier
from .helpers import assert_result_valid


def _instance() -> Team:
    """Big enough that the symmetry actually costs something to search through."""
    return Team(
        dancers=roster(10, 12),
        surveys=[
            desired("led0", tier(1, "fol0", "fol1"), tier(2, "fol2")),
            desired("led1", tier(1, "fol1"), tier(2, "fol3")),
            desired("led2", tier(1, "fol4")),
            desired("led5", tier(1, "fol0")),
            not_desired("led3", tier(1, "fol5")),
            desired("fol0", tier(1, "led0")),
            desired("fol6", tier(1, "led4", "led5")),
            not_desired("fol7", tier(1, "led6")),
        ],
        n_positions=8,
    )


def test_symmetry_breaking_does_not_change_the_optimum() -> None:
    instance = _instance()
    config = SolverConfig()
    constrained = solve(instance, config, break_symmetry=True)
    free = solve(instance, config, break_symmetry=False)

    assert_result_valid(constrained, instance, config)
    assert_result_valid(free, instance, config)
    assert [stage.value for stage in constrained.stages] == [stage.value for stage in free.stages]
    assert constrained.best.total_score == free.best.total_score
    assert constrained.best.min_score == free.best.min_score


def test_symmetry_breaking_reduces_the_search() -> None:
    instance = _instance()
    config = SolverConfig()
    constrained = solve(instance, config, break_symmetry=True)
    free = solve(instance, config, break_symmetry=False)
    # Branch count rather than wall clock: it is the solver's own measure of work done and
    # does not flake on a loaded CI machine.
    assert constrained.num_branches < free.num_branches


# The canonical-numbering assertions below must look at the solver's own solution, not at the
# ranked shortlist: `solver._ranking_key` orders the enumerated ties by a string built from the
# dancer ids per position, which imposes an order of its own and would mask a missing constraint.
CANONICAL = SolverConfig(max_solutions=1)


def test_canonical_numbering_puts_the_first_leader_on_position_a() -> None:
    # Asserted across the whole shortlist, not just the best solution: the constraint forces
    # `x[leader_0, p] == 0` for every p > 0, so *no* admissible assignment may place led0 elsewhere.
    # Checking only one solution would pass by luck even with the constraint deleted.
    instance = _instance()
    result = solve(instance, SolverConfig(max_solutions=30), break_symmetry=True)
    assert len(result.solutions) > 1, "the instance must have several optima to be a real test"
    for solution in result.solutions:
        assert "led0" in solution.positions[0].leaders


def test_canonical_numbering_fills_positions_in_order() -> None:
    instance = _instance()
    result = solve(instance, CANONICAL, break_symmetry=True)
    leaders = [dancer.id for dancer in instance.by_role(Role.LEADER)]
    first_seen: list[int] = []
    for position in result.best.positions:
        indices = [leaders.index(i) for i in position.leaders]
        first_seen.append(min(indices))
    # Position p may only be opened by a leader later in the input than the one that opened
    # position p-1, which is exactly what the constraint encodes.
    assert first_seen == sorted(first_seen)
    assert len(set(first_seen)) == len(first_seen)
