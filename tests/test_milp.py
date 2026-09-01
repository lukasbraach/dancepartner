"""The small modelling layer the HiGHS backend is built on (``dancepartner._milp``).

Tested directly rather than only through the solver: these are the pieces where a quiet mistake
-- a dropped row, a mis-evaluated expression, a status reported as success -- would surface far
away as "the two backends disagree", and be hard to trace back from there.
"""

from __future__ import annotations

import pytest

from dancepartner._milp import Expr, Model

pytest.importorskip("highspy")


def _model() -> Model:
    return Model(seed=0, time_limit=10.0, log=False)


# -- expressions ------------------------------------------------------------------------------


def test_expressions_add_subtract_and_scale() -> None:
    a, b = Expr.of(0), Expr.of(1)
    combined = a * 3 + b - 2
    assert combined.coeffs == {0: 3, 1: 1}
    assert combined.constant == -2
    assert (2 - a).coeffs == {0: -1}
    assert (2 - a).constant == 2
    assert (-combined).constant == 2


def test_repeated_terms_are_merged_not_dropped() -> None:
    """``a + a`` is ``2a``. A dict keyed by column would silently keep only the last one."""
    doubled = Expr.of(0) + Expr.of(0)
    assert doubled.coeffs == {0: 2}


def test_an_expression_evaluates_at_a_solution() -> None:
    expr = Expr.of(0, 3) + Expr.of(1, -2) + 5
    assert expr.value([1.0, 2.0]) == 4
    # HiGHS returns integers as floats a hair off; the value has to round, not truncate.
    assert expr.value([0.9999999, 2.0000001]) == 4


def test_summing_nothing_is_a_constant_zero() -> None:
    assert Expr.sum([]).coeffs == {}
    assert Expr.sum([]).value([]) == 0


# -- rows -------------------------------------------------------------------------------------


def test_a_tautological_constant_row_is_dropped() -> None:
    """An instance where nobody stated a preference has an all-zero objective to pin."""
    model = _model()
    model.add(Expr(), lo=0)
    model.equal(Expr(), 0)
    assert model.h.getNumRow() == 0


def test_an_unsatisfiable_constant_row_is_refused() -> None:
    """HiGHS would accept it and hand back an infeasible model with no explanation."""
    model = _model()
    with pytest.raises(ValueError, match="unsatisfiable constant row"):
        model.equal(Expr(), 1)
    with pytest.raises(ValueError, match="unsatisfiable constant row"):
        model.add(Expr() + 5, hi=1)


# -- solving ----------------------------------------------------------------------------------


def test_a_solved_model_reports_optimal_and_its_values() -> None:
    model = _model()
    a, b = model.binary(), model.binary()
    model.add(Expr.of(a) + Expr.of(b), hi=1)
    objective = Expr.of(a, 3) + Expr.of(b, 2)
    assert model.optimize(objective, maximize=True)
    assert model.status_name == "OPTIMAL"
    assert model.value(objective) == 3
    assert model.is_set(a) and not model.is_set(b)
    assert model.solution == [1.0, 0.0]


def test_an_infeasible_model_says_so_rather_than_returning_a_solution() -> None:
    model = _model()
    a = model.binary()
    model.equal(Expr.of(a), 1)
    model.equal(Expr.of(a), 0)
    assert not model.optimize(Expr.of(a), maximize=True)
    assert model.status_name == "INFEASIBLE"


def test_the_objective_is_replaced_between_solves_not_added_to() -> None:
    """A staged objective would otherwise accumulate every earlier stage's costs."""
    model = _model()
    a, b = model.binary(), model.binary()
    model.add(Expr.of(a) + Expr.of(b), hi=1)
    assert model.optimize(Expr.of(a, 10), maximize=True)
    assert model.is_set(a)
    assert model.optimize(Expr.of(b, 1), maximize=True)
    assert model.is_set(b) and not model.is_set(a), "the first stage's cost is still in play"


def test_a_row_added_after_a_solve_binds_on_the_next_one() -> None:
    """The whole staging design rests on this."""
    model = _model()
    a, b = model.binary(), model.binary()
    objective = Expr.of(a, 3) + Expr.of(b, 2)
    assert model.optimize(objective, maximize=True)
    assert model.value(objective) == 5
    model.equal(Expr.of(a), 0)
    assert model.optimize(objective, maximize=True)
    assert model.value(objective) == 2


def test_work_counters_are_reported() -> None:
    model = _model()
    a = model.binary()
    model.optimize(Expr.of(a), maximize=True)
    assert model.wall_time >= 0.0
    assert model.num_nodes >= 0


class _StatusStub:
    """Stands in for HiGHS so the statuses a fast test cannot provoke are still checked."""

    def __init__(self, status: object, *, has_primal: bool = False) -> None:
        self._status = status
        self._has_primal = has_primal

    def getModelStatus(self) -> object:  # noqa: N802 -- mirrors the HiGHS method name
        return self._status

    def getInfo(self) -> object:  # noqa: N802 -- mirrors the HiGHS method name
        return type("Info", (), {"primal_solution_status": int(self._has_primal)})()


def test_an_unrecognised_status_is_not_reported_as_success() -> None:
    """Anything the mapping does not know about must read as UNKNOWN, never as a solution."""
    import highspy

    model = _model()
    model.h = _StatusStub(highspy.HighsModelStatus.kUnbounded)
    assert model.status_name == "UNKNOWN"


def test_a_timed_out_solve_is_feasible_only_when_it_actually_found_something() -> None:
    """CP-SAT's vocabulary: FEASIBLE means "valid but not proven best", not "gave up".

    Reachable in practice only by exhausting a time limit on a hard instance, which is not
    something a test suite can afford to wait for -- hence the stub.
    """
    import highspy

    limit = highspy.HighsModelStatus.kTimeLimit
    model = _model()
    model.h = _StatusStub(limit, has_primal=True)
    assert model.status_name == "FEASIBLE"
    model.h = _StatusStub(limit, has_primal=False)
    assert model.status_name == "UNKNOWN"
