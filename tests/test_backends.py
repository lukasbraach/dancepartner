"""Backend selection: which solver runs, and what happens when the choice is impossible.

SPEC.md 8.1 and 14.2. The point of the dispatcher is that asking *which* solver is available
never imports one -- that is what lets the browser build ship ``dancepartner.solver`` for its
result types while installing only HiGHS.
"""

from __future__ import annotations

import pytest

from dancepartner import solver
from dancepartner.model import SolverConfig, Team
from dancepartner.results import SolveResult


@pytest.fixture
def no_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run without an inherited DANCEPARTNER_BACKEND."""
    monkeypatch.delenv(solver.ENV_VAR, raising=False)


def test_cpsat_is_the_default_where_ortools_is_installed(no_env: None) -> None:
    """The reference implementation wins when both are available (SPEC.md 8)."""
    pytest.importorskip("ortools")
    assert solver.available_backends()[0] == "cpsat"
    assert solver.resolve_backend() == "cpsat"


def test_an_explicit_choice_beats_the_default(no_env: None) -> None:
    pytest.importorskip("ortools")
    assert solver.resolve_backend("cpsat") == "cpsat"


def test_the_environment_overrides_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("ortools")
    monkeypatch.setenv(solver.ENV_VAR, "cpsat")
    assert solver.resolve_backend() == "cpsat"


def test_an_unknown_backend_is_rejected_by_name(no_env: None) -> None:
    with pytest.raises(ValueError, match="unknown backend"):
        solver.resolve_backend("glpk")


def test_a_known_but_uninstalled_backend_says_what_is_missing(
    no_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The message has to name the package, or the coach cannot act on it."""
    monkeypatch.setattr(solver, "_installed", lambda package: False)
    with pytest.raises(ValueError, match="highspy"):
        solver.resolve_backend("highs")


def test_no_backend_at_all_is_an_error_not_a_crash(
    no_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(solver, "_installed", lambda package: False)
    assert solver.available_backends() == []
    with pytest.raises(ValueError, match="no solver backend installed"):
        solver.resolve_backend()


def test_probing_never_raises_even_when_find_spec_does() -> None:
    """``find_spec`` raises for a missing parent package; the answer we want is still "no"."""

    def explode(package: str) -> bool:
        raise ImportError(package)

    import importlib.util

    original = importlib.util.find_spec
    try:
        importlib.util.find_spec = explode  # type: ignore[assignment]
        assert solver._installed("anything") is False
    finally:
        importlib.util.find_spec = original


def test_the_result_records_which_backend_produced_it(no_env: None, tiny: Team) -> None:
    """``solve --json`` carries it, so a stored result says how it was computed."""
    pytest.importorskip("ortools")
    result: SolveResult = solver.solve(tiny, SolverConfig(max_solutions=1))
    assert result.backend == "cpsat"


def test_the_dispatcher_imports_no_backend_by_itself() -> None:
    """Importing this module must stay free of ortools -- the browser build depends on it."""
    import subprocess
    import sys

    code = (
        "import sys; import dancepartner.solver;"
        " assert not any(m.startswith('ortools') for m in sys.modules), sorted(sys.modules)"
    )
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stderr
