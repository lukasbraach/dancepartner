"""Solver-agnostic result types and the staged-objective vocabulary.

Split out of :mod:`dancepartner.solver` so that neither solver backend is needed to *describe*
a solve. That is what lets the browser build ship the result types, the CLI's JSON contract and
the UI's type annotations without dragging in a solver it cannot install (SPEC.md 14.2).

Nothing here imports ortools or highspy, and nothing here should.
"""

from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass
from enum import Enum
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

from .feasibility import FeasibilityIssue
from .model import Objective, SolverConfig
from .scoring import Solution

__all__ = [
    "InfeasibleInstanceError",
    "Sense",
    "SolveResult",
    "Stage",
    "StageResult",
    "StageSource",
    "ranking_key",
]

E = TypeVar("E")
"""One backend's expression type: a CP-SAT ``LinearExpr``, a HiGHS linear expression."""


class Sense(Enum):
    """Optimisation direction of one objective stage."""

    MAXIMIZE = "maximize"
    MINIMIZE = "minimize"


@dataclass(frozen=True)
class Stage(Generic[E]):
    """One step of the staged objective.

    Attributes:
        name: Stable identifier, used in logs and in ``SolveResult.stages``.
        expr: What to optimise.
        sense: Which direction.
        slack: How far a later stage may walk this one's optimum back. Only
            ``LEXICOGRAPHIC_TIERS`` uses it (SPEC.md 8's epsilon).
        surrogate: ``expr`` is an artificial bound variable (a maximin floor), not a quantity
            with meaning of its own. Such a variable is otherwise free once the objective is
            gone, so the enumeration pass pins it to a single value instead of a range --
            without that, CP-SAT reports the same assignment once per admissible floor value
            and burns the shortlist on duplicates.
        tie_break: This stage exists only to choose between equally good assignments and must
            never make an earlier stage worse. Before it runs, every earlier stage that was
            pinned with slack is re-pinned at the value it actually achieved, so the tie-break
            cannot spend somebody else's epsilon. See ``_run_stages``.
    """

    name: str
    expr: E
    sense: Sense
    slack: int = 0
    surrogate: bool = False
    tie_break: bool = False


StageSource = Generator[Stage[E], int, None]
"""Yields stages, receives each achieved optimum. See the module docstring."""


class InfeasibleInstanceError(ValueError):
    """The counting pre-checks rejected the instance before the solver ran."""

    def __init__(self, issues: list[FeasibilityIssue]) -> None:
        """Store the issues and build an English exception message carrying them."""
        self.issues = issues
        joined = "; ".join(f"[{issue.code}] {issue.message}" for issue in issues)
        super().__init__(f"instance is infeasible by counting: {joined}")


class StageResult(BaseModel):
    """The outcome of one objective stage."""

    model_config = ConfigDict(frozen=True)

    name: str
    sense: Sense
    value: int
    locked_at: int | None = None
    """The floor this stage was finally guaranteed, when a later stage was allowed to walk its
    optimum back (``SolverConfig.tier_slack``). ``None`` -- the default -- means nothing was
    ever allowed to, so the guarantee is ``value`` itself.

    It is a floor, not a final figure: the enumeration pass may well find an assignment
    that does better than the one pass 1 happened to stop at, and it is free to."""


class SolveResult(BaseModel):
    """Everything a solve produced.

    Attributes:
        backend: Which solver produced this -- ``"cpsat"`` or ``"highs"`` (SPEC.md 8.1).
        status: Solver status name of the final optimisation stage.
        solutions: The shortlist, best first. One entry when ``max_solutions == 1``, otherwise
            the deduplicated optimal (or near-optimal) assignments found within the caps.
        stages: Per-stage objective values, in the order they were optimised.
        truncated: The enumeration hit ``max_solutions`` or its time limit, so the shortlist is
            a sample of the optima rather than all of them.
        wall_time: Total solver wall time across every pass, in seconds.
        num_branches: Total branches explored across every pass.
    """

    model_config = ConfigDict(frozen=True)

    backend: str = ""
    status: str
    solutions: list[Solution]
    stages: list[StageResult] = []
    truncated: bool = False
    wall_time: float = 0.0
    num_branches: int = 0

    @property
    def best(self) -> Solution:
        """The best solution found; raises if there is none."""
        if not self.solutions:
            raise ValueError(f"no solution found (status {self.status})")
        return self.solutions[0]


def ranking_key(solution: Solution, config: SolverConfig) -> tuple[int, int, str]:
    """Order the shortlist best first, deterministically.

    With the default ``near_optimal_ratio`` of 1.0 every entry has the same scores, so only the
    tie-break matters and it exists to keep the order reproducible across runs.
    """
    fairness_first = config.objective in (Objective.MAXIMIN_THEN_SUM, Objective.LEXIMIN)
    primary = -solution.min_score if fairness_first else -solution.total_score
    secondary = -solution.total_score if fairness_first else -solution.min_score
    tie_break = "|".join(
        ",".join(sorted((*position.leaders, *position.followers)))
        for position in solution.positions
    )
    return (primary, secondary, tie_break)
