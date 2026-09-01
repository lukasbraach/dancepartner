"""Backend selection, and the public ``solve`` entry point.

There are two solvers behind this module. CP-SAT (:mod:`dancepartner.cpsat`) is the reference
implementation and what the performance figures are measured on. HiGHS
(:mod:`dancepartner.highs`) is a MILP formulation of the same model, and the only one of the two
with a WebAssembly wheel -- which is what lets the browser build compute an assignment at all
(SPEC.md 14.2).

**This module imports neither.** Both are pulled in lazily inside :func:`solve`, so importing
``dancepartner.solver`` -- for ``SolveResult``, for a type annotation, for the CLI's JSON
contract -- never drags a solver in. That is what makes the module shippable to a browser that
can install only one of the two.

Selection order: the explicit ``backend`` argument, then ``DANCEPARTNER_BACKEND``, then the
first importable backend in :data:`_PREFERENCE`. Every result records which one ran.
"""

from __future__ import annotations

import importlib
import importlib.util
import os
from types import ModuleType
from typing import Final

from .model import SolverConfig, Team
from .results import (
    InfeasibleInstanceError,
    Sense,
    SolveResult,
    Stage,
    StageResult,
    StageSource,
    ranking_key,
)

__all__ = [
    "InfeasibleInstanceError",
    "Sense",
    "SolveResult",
    "Stage",
    "StageResult",
    "StageSource",
    "available_backends",
    "ranking_key",
    "resolve_backend",
    "solve",
]

ENV_VAR: Final = "DANCEPARTNER_BACKEND"
"""Overrides the default backend. Read per call, unlike ``DANCEPARTNER_LANG``."""

_PREFERENCE: Final = ("cpsat", "highs")
"""Tried in order. CP-SAT first: it is the reference implementation (SPEC.md 8)."""

_REQUIRES: Final = {"cpsat": "ortools", "highs": "highspy"}
"""The third-party package each backend needs, probed without importing it."""


def _installed(package: str) -> bool:
    """Whether ``package`` could be imported, without importing it.

    ``find_spec`` returns ``None`` for a plainly absent top-level package, but it *raises* when
    a parent package is missing or a meta-path finder objects. Either way the answer we want is
    "no", and asking must never be able to break a caller.
    """
    try:
        return importlib.util.find_spec(package) is not None
    except (ImportError, ValueError):
        return False


def available_backends() -> list[str]:
    """The backends installable here, in preference order.

    Probed rather than imported: asking must stay cheap, and must not drag a solver in as a
    side effect of asking.
    """
    return [name for name in _PREFERENCE if _installed(_REQUIRES[name])]


def resolve_backend(backend: str | None = None) -> str:
    """Decide which backend to use, without importing it.

    Args:
        backend: An explicit choice, or ``None`` to consult the environment and availability.

    Returns:
        The chosen backend name.

    Raises:
        ValueError: The name is not a backend, or nothing usable is installed.
    """
    chosen = backend or os.environ.get(ENV_VAR) or ""
    if chosen:
        if chosen not in _PREFERENCE:
            raise ValueError(f"unknown backend {chosen!r}; expected one of {_PREFERENCE}")
        if not _installed(_REQUIRES[chosen]):
            missing = _REQUIRES[chosen]
            raise ValueError(f"backend {chosen!r} needs {missing}, which is not installed")
        return chosen

    usable = available_backends()
    if not usable:
        needed = sorted(_REQUIRES.values())
        raise ValueError(f"no solver backend installed; one of {needed} is needed")
    return usable[0]


def _load(name: str) -> ModuleType:
    """Import one backend module. Deferred, so this module stays solver-free."""
    return importlib.import_module(f".{name}", __package__)


def solve(
    team: Team,
    config: SolverConfig | None = None,
    *,
    skip_precheck: bool = False,
    break_symmetry: bool = True,
    backend: str | None = None,
) -> SolveResult:
    """Solve the assignment problem and return a shortlist of optima.

    Args:
        team: The instance.
        config: Solver configuration; defaults to ``SolverConfig()``.
        skip_precheck: Skip ``feasibility.check_feasibility``. Only for tests that want to see
            how the solver reacts to an instance the counting checks already reject.
        break_symmetry: Add the canonical position numbering. Off only for the test that
            asserts symmetry breaking does not change the optimum.
        backend: ``"cpsat"``, ``"highs"``, or ``None`` to choose automatically.

    Returns:
        The result, with ``backend`` recording which solver produced it.

    Raises:
        InfeasibleInstanceError: The counting pre-checks found an obstruction.
        ValueError: The requested backend is unknown or not installed.
    """
    module = _load(resolve_backend(backend))
    result: SolveResult = module.solve(
        team, config, skip_precheck=skip_precheck, break_symmetry=break_symmetry
    )
    return result
