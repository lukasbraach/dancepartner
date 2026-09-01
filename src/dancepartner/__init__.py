"""``dancepartner`` -- exact assignment of a Latin formation team to its positions.

Public surface. The core is UI-agnostic on purpose: nothing under ``dancepartner`` imports
``streamlit``, and a reviewer can delete ``app/`` and still run everything.

``solve`` is re-exported lazily (SPEC.md 14.2). Importing any submodule runs this module first,
so an eager import of a *backend* would put ortools -- which has no WebAssembly wheel -- in the
browser build's dependency set, and the data model would become unimportable there.

``solver`` itself is safe to import eagerly: since the backends were split out it dispatches
between them without importing either, so the result types come along for free. Only the
function that actually reaches a backend stays deferred.
"""

from typing import TYPE_CHECKING, Any, Final

from .feasibility import FeasibilityIssue, check_feasibility, veto_pairs
from .i18n import Language, get_language, set_language, t
from .model import (
    DEFAULT_N_POSITIONS,
    Dancer,
    Objective,
    PreferenceEntry,
    PreferenceScope,
    Role,
    SolverConfig,
    Survey,
    Team,
    Tier,
    position_label,
    position_labels,
)
from .results import InfeasibleInstanceError, SolveResult
from .scoring import (
    DancerSatisfaction,
    PositionAssignment,
    Solution,
    build_satisfaction,
    build_solution,
    build_weights,
    scored_pairs,
)
from .storage import (
    MalformedYamlError,
    StorageError,
    dump_team,
    load_team,
    parse_team,
    save_team,
)

if TYPE_CHECKING:  # mypy binds the real type; at runtime __getattr__ below does the work.
    from .solver import solve

_LAZY: Final = frozenset({"solve"})
"""Resolved from :mod:`dancepartner.solver` on first use, rather than at import."""

__all__ = [
    "DEFAULT_N_POSITIONS",
    "Dancer",
    "DancerSatisfaction",
    "FeasibilityIssue",
    "InfeasibleInstanceError",
    "Language",
    "MalformedYamlError",
    "Objective",
    "PositionAssignment",
    "PreferenceEntry",
    "PreferenceScope",
    "Role",
    "SolveResult",
    "Solution",
    "SolverConfig",
    "StorageError",
    "Survey",
    "Team",
    "Tier",
    "build_satisfaction",
    "build_solution",
    "build_weights",
    "check_feasibility",
    "dump_team",
    "get_language",
    "load_team",
    "parse_team",
    "position_label",
    "position_labels",
    "save_team",
    "scored_pairs",
    "set_language",
    "solve",
    "t",
    "veto_pairs",
]


def __getattr__(name: str) -> Any:  # noqa: ANN401
    """Resolve ``solve`` on first access, then cache it in the module namespace.

    Args:
        name: The attribute being looked up.

    Returns:
        The object of that name from :mod:`dancepartner.solver`.

    Raises:
        AttributeError: ``name`` is not one of the deferred names.
    """
    if name in _LAZY:
        from . import solver

        value = getattr(solver, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    """List the deferred names too, so ``dir(dancepartner)`` stays honest before first use."""
    return sorted(set(globals()) | _LAZY)
