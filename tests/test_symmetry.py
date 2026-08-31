"""Symmetry breaking must not change the optimum, only the work needed to prove it.

Positions are unordered, so the 8! = 40320 relabellings of any assignment are all equally
good. The canonical numbering removes them from the search space.
"""

from __future__ import annotations

from dancepartner.model import Role, SolverConfig, Team
from dancepartner.solver import solve

from .builders import nicht_wunsch, roster, tier, wunsch
from .helpers import assert_result_valid


def _instance() -> Team:
    """Big enough that the symmetry actually costs something to search through."""
    return Team(
        dancers=roster(10, 12),
        surveys=[
            wunsch("h0", tier(1, "d0", "d1"), tier(2, "d2")),
            wunsch("h1", tier(1, "d1"), tier(2, "d3")),
            wunsch("h2", tier(1, "d4")),
            wunsch("h5", tier(1, "d0")),
            nicht_wunsch("h3", tier(1, "d5")),
            wunsch("d0", tier(1, "h0")),
            wunsch("d6", tier(1, "h4", "h5")),
            nicht_wunsch("d7", tier(1, "h6")),
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


def test_canonical_numbering_puts_the_first_herr_on_position_a() -> None:
    # Asserted across the whole shortlist, not just the best solution: the constraint forces
    # `x[herr_0, p] == 0` for every p > 0, so *no* admissible assignment may place h0 elsewhere.
    # Checking only one solution would pass by luck even with the constraint deleted.
    instance = _instance()
    result = solve(instance, SolverConfig(max_solutions=30), break_symmetry=True)
    assert len(result.solutions) > 1, "the instance must have several optima to be a real test"
    for solution in result.solutions:
        assert "h0" in solution.positions[0].herren


def test_canonical_numbering_fills_positions_in_order() -> None:
    instance = _instance()
    result = solve(instance, CANONICAL, break_symmetry=True)
    herren = [dancer.id for dancer in instance.by_role(Role.HERR)]
    first_seen: list[int] = []
    for position in result.best.positions:
        indices = [herren.index(i) for i in position.herren]
        first_seen.append(min(indices))
    # Position p may only be opened by a Herr later in the input than the one that opened
    # position p-1, which is exactly what the constraint encodes.
    assert first_seen == sorted(first_seen)
    assert len(set(first_seen)) == len(first_seen)
