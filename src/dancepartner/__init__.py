"""``dancepartner`` -- exact assignment of a Latin formation team to its positions.

Public surface. The core is UI-agnostic on purpose: nothing under ``dancepartner`` imports
``streamlit``, and a reviewer can delete ``app/`` and still run everything.

The three solver names are re-exported lazily (SPEC.md 14). Importing any submodule runs this
module first, so an eager ``from .solver import ...`` would put ortools -- which has no
WebAssembly wheel -- in the browser build's dependency set, and the data model would become
unimportable there. Everything else is a plain eager re-export.
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

if TYPE_CHECKING:  # mypy binds the real types; at runtime __getattr__ below does the work.
    from .solver import InfeasibleInstanceError, SolveResult, solve

_LAZY: Final = frozenset({"InfeasibleInstanceError", "SolveResult", "solve"})
"""Names resolved from :mod:`dancepartner.solver` on first use, rather than at import."""

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
    """Resolve a solver name on first access, then cache it in the module namespace.

    Args:
        name: The attribute being looked up.

    Returns:
        The object of that name from :mod:`dancepartner.solver`.

    Raises:
        AttributeError: ``name`` is not one of the deferred solver names.
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
