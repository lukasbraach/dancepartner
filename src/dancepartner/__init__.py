"""``dancepartner`` -- exact assignment of a Latin formation team to its positions.

Public surface. The core is UI-agnostic on purpose: nothing under ``dancepartner`` imports
``streamlit``, and a reviewer can delete ``app/`` and still run everything.
"""

from .feasibility import FeasibilityIssue, check_feasibility, veto_pairs
from .i18n import de
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
    WeightScheme,
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
from .solver import InfeasibleInstanceError, SolveResult, solve
from .storage import (
    MalformedYamlError,
    StorageError,
    dump_team,
    load_team,
    parse_team,
    save_team,
)

__all__ = [
    "DEFAULT_N_POSITIONS",
    "Dancer",
    "DancerSatisfaction",
    "FeasibilityIssue",
    "InfeasibleInstanceError",
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
    "WeightScheme",
    "build_satisfaction",
    "build_solution",
    "build_weights",
    "check_feasibility",
    "de",
    "dump_team",
    "load_team",
    "parse_team",
    "position_label",
    "position_labels",
    "save_team",
    "scored_pairs",
    "solve",
    "veto_pairs",
]
