"""A small linear-expression and model layer over HiGHS.

Just enough to express SPEC.md 8's model as a MILP: integer columns, linear rows, an objective
that can be replaced between solves, and evaluation of an expression at the current solution.

Written against HiGHS's low-level ``addCol``/``addRow`` interface rather than its modelling
sugar, because the staged objectives need three things the sugar does not promise across
versions: replacing the objective on an already-solved model, adding a row and re-solving
without rebuilding, and reading an arbitrary expression's value back out of a solution.

Coefficients are integers throughout -- SPEC.md 8 keeps the objective in integer arithmetic so
that halving never rounds -- and are only widened to float at the HiGHS boundary.
"""

from __future__ import annotations

from typing import Final

import highspy
import numpy as np

INF: Final = highspy.kHighsInf


class Expr:
    """A linear expression over column indices, with an integer constant term."""

    __slots__ = ("coeffs", "constant")

    def __init__(self, coeffs: dict[int, int] | None = None, constant: int = 0) -> None:
        """Build an expression from a column-to-coefficient mapping and a constant."""
        self.coeffs: dict[int, int] = dict(coeffs or {})
        self.constant = constant

    @classmethod
    def of(cls, column: int, coefficient: int = 1) -> Expr:
        """One term."""
        return cls({column: coefficient})

    @classmethod
    def sum(cls, parts: list[Expr]) -> Expr:
        """Add up any number of expressions."""
        total = cls()
        for part in parts:
            total += part
        return total

    def __add__(self, other: Expr | int) -> Expr:
        if isinstance(other, int):
            return Expr(self.coeffs, self.constant + other)
        merged = dict(self.coeffs)
        for column, coefficient in other.coeffs.items():
            merged[column] = merged.get(column, 0) + coefficient
        return Expr(merged, self.constant + other.constant)

    __radd__ = __add__

    def __neg__(self) -> Expr:
        return Expr({c: -v for c, v in self.coeffs.items()}, -self.constant)

    def __sub__(self, other: Expr | int) -> Expr:
        return self + (-other if isinstance(other, Expr) else -other)

    def __rsub__(self, other: Expr | int) -> Expr:
        return (-self) + other

    def __mul__(self, factor: int) -> Expr:
        return Expr({c: v * factor for c, v in self.coeffs.items()}, self.constant * factor)

    __rmul__ = __mul__

    def value(self, columns: list[float]) -> int:
        """Evaluate at a solution. Rounded: HiGHS returns integers as floats near the integer."""
        total = float(self.constant)
        for column, coefficient in self.coeffs.items():
            total += coefficient * columns[column]
        return round(total)


class Model:
    """A MILP under construction, and the solved state that goes with it."""

    def __init__(self, *, seed: int, time_limit: float, log: bool) -> None:
        """Start an empty model with the reproducibility settings SPEC.md 8 asks for."""
        self.h = highspy.Highs()
        self.h.setOptionValue("output_flag", log)
        self.h.setOptionValue("random_seed", seed)
        # Enumeration and reproducibility both need a deterministic search, and Pyodide has no
        # threads to use anyway.
        self.h.setOptionValue("threads", 1)
        self.h.setOptionValue("time_limit", time_limit)
        # These are exact combinatorial problems; the default gap would stop early on a
        # solution that is merely close, and the staged pins would then be wrong.
        self.h.setOptionValue("mip_rel_gap", 0.0)
        self.h.setOptionValue("mip_abs_gap", 0.0)
        self._columns = 0
        self._solution: list[float] = []
        self._solution_columns = 0

    # -- building ------------------------------------------------------------------------

    def integer(self, lo: int, hi: int) -> int:
        """Add an integer column and return its index."""
        self.h.addCol(0.0, float(lo), float(hi), 0, _EMPTY_I, _EMPTY_F)
        index = self._columns
        self._columns += 1
        self.h.changeColIntegrality(index, highspy.HighsVarType.kInteger)
        return index

    def binary(self) -> int:
        """Add a 0/1 column and return its index."""
        return self.integer(0, 1)

    def add(self, expr: Expr, *, lo: int | None = None, hi: int | None = None) -> None:
        """Constrain ``lo <= expr <= hi``.

        A constant expression is legitimate -- an instance where nobody stated a preference has
        an all-zero objective, and pinning it is a tautology -- so such a row is dropped rather
        than sent to HiGHS.

        Raises:
            ValueError: The expression is constant *and* violates the bound. HiGHS would accept
                that row and quietly return an infeasible model; it can only mean the caller
                built the expression wrong, and a loud failure beats a solve that returns
                nothing for no visible reason.
        """
        lower = -INF if lo is None else float(lo - expr.constant)
        upper = INF if hi is None else float(hi - expr.constant)
        if not expr.coeffs:
            if (lo is not None and expr.constant < lo) or (hi is not None and expr.constant > hi):
                raise ValueError(f"unsatisfiable constant row: {expr.constant} in [{lo}, {hi}]")
            return
        columns = np.fromiter(expr.coeffs.keys(), dtype=np.int32, count=len(expr.coeffs))
        values = np.fromiter((float(v) for v in expr.coeffs.values()), dtype=float)
        self.h.addRow(lower, upper, len(expr.coeffs), columns, values)

    def equal(self, expr: Expr, value: int) -> None:
        """Constrain ``expr == value``."""
        self.add(expr, lo=value, hi=value)

    # -- solving -------------------------------------------------------------------------

    def optimize(self, expr: Expr, *, maximize: bool) -> bool:
        """Replace the objective, solve, and report whether a solution came back.

        Every column's cost is rewritten, not just the ones in ``expr``: a stage's objective
        has to *replace* the previous stage's, not add to it.
        """
        costs = np.zeros(self._columns, dtype=float)
        for column, coefficient in expr.coeffs.items():
            costs[column] = float(coefficient)
        self.h.changeColsCost(self._columns, np.arange(self._columns, dtype=np.int32), costs)
        sense = highspy.ObjSense.kMaximize if maximize else highspy.ObjSense.kMinimize
        self.h.changeObjectiveSense(sense)
        self._warm_start()
        self.h.run()
        if not self.usable:
            return False
        self._solution = list(self.h.getSolution().col_value)
        self._solution_columns = self._columns
        return True

    def _warm_start(self) -> None:
        """Offer the previous stage's assignment as a starting point.

        A staged objective solves the same model over and over with one more row each time, and
        the previous stage's solution almost always still satisfies that row -- a pin is placed
        at the value that solution achieved. Handing it over turns "find a feasible point from
        scratch" into "improve on this one", which is the difference between finishing and
        hitting the time limit on the hard instances.

        Skipped when columns have been added since, because the stored vector no longer
        describes the model. Padding it would be guessing, and HiGHS would only reject the
        result -- the stages that add columns are the ones that build fresh indicator variables
        for a new leximin round.
        """
        if not self._solution or self._solution_columns != self._columns:
            return
        start = highspy.HighsSolution()
        start.col_value = self._solution
        self.h.setSolution(start)

    @property
    def usable(self) -> bool:
        """Whether the last solve produced an assignment worth reading."""
        status = self.h.getModelStatus()
        return status in (
            highspy.HighsModelStatus.kOptimal,
            highspy.HighsModelStatus.kTimeLimit,
        ) and bool(self.h.getInfo().primal_solution_status)

    @property
    def status_name(self) -> str:
        """The last solve's status, in CP-SAT's vocabulary so both backends read alike."""
        status = self.h.getModelStatus()
        if status == highspy.HighsModelStatus.kOptimal:
            return "OPTIMAL"
        if status == highspy.HighsModelStatus.kInfeasible:
            return "INFEASIBLE"
        if status == highspy.HighsModelStatus.kTimeLimit:
            return "FEASIBLE" if self.h.getInfo().primal_solution_status else "UNKNOWN"
        return "UNKNOWN"

    @property
    def solution(self) -> list[float]:
        """Column values of the last usable solve."""
        return self._solution

    def value(self, expr: Expr) -> int:
        """Evaluate ``expr`` at the last solution."""
        return expr.value(self._solution)

    def is_set(self, column: int) -> bool:
        """Whether a binary column came back as 1. Tolerant of HiGHS's float output."""
        return self._solution[column] > 0.5

    @property
    def wall_time(self) -> float:
        """Seconds spent in the last solve."""
        return float(self.h.getRunTime())

    @property
    def num_nodes(self) -> int:
        """Branch-and-bound nodes of the last solve, reported as CP-SAT's ``num_branches``."""
        return int(self.h.getInfo().mip_node_count or 0)


_EMPTY_I: Final = np.array([], dtype=np.int32)
_EMPTY_F: Final = np.array([], dtype=float)
