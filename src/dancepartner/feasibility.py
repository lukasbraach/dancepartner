"""Cheap counting pre-checks, run before the CP-SAT model is built.

The solver must never answer a question that arithmetic already settles: a bare INFEASIBLE
tells the coach nothing, while "du hast 5 Herren mit Startanspruch, aber nur 4 Positionen
mit einfacher Herrenbesetzung" tells them exactly which flag to change.

German diagnostics live in :mod:`dancepartner.i18n`, keyed ``feasibility.<code>``.

These checks are **necessary, not sufficient**. Passing them does not prove the instance is
solvable; CP-SAT remains the authority on infeasibility. Every check here is a pure counting
argument, so a reported issue is always a real one.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from .i18n import de
from .model import Role, SolverConfig, Team, ceil_div

__all__ = ["FeasibilityIssue", "check_feasibility", "veto_pairs"]

_ROLE_DE = {Role.HERR: de("role.herr.plural"), Role.DAME: de("role.dame.plural")}


class FeasibilityIssue(BaseModel):
    """One decidable-by-counting reason the instance cannot be solved.

    Attributes:
        code: Stable machine-readable identifier, English.
        message_de: German explanation for the coach.
        involved_ids: Dancer ids the issue is about; empty when it is purely about counts.
    """

    model_config = ConfigDict(frozen=True)

    code: str
    message_de: str
    involved_ids: tuple[str, ...] = ()


def _issue(code: str, involved_ids: tuple[str, ...] = (), **params: object) -> FeasibilityIssue:
    return FeasibilityIssue(
        code=code, message_de=de(f"feasibility.{code}", **params), involved_ids=involved_ids
    )


def veto_pairs(team: Team, config: SolverConfig) -> set[frozenset[str]]:
    """Unordered dancer pairs that must not share a position.

    A veto is symmetric even though preferences are not: if A vetoes B at the configured
    tier, the pair cannot share a position, whatever B wrote about A.
    """
    pairs: set[frozenset[str]] = set()
    for entry in team.preference_entries(config.scope):
        if entry.direction == "nicht_wunsch" and config.vetoed_ranks(entry.rank):
            pairs.add(frozenset((entry.source, entry.target)))
    return pairs


def check_feasibility(team: Team, config: SolverConfig | None = None) -> list[FeasibilityIssue]:
    """Return every counting obstruction found, empty list if none.

    Args:
        team: The instance to check.
        config: Solver configuration; only ``veto_tier`` and ``scope`` matter here. Defaults
            to ``SolverConfig()``.
    """
    config = config or SolverConfig()
    issues: list[FeasibilityIssue] = []
    issues.extend(_check_role_counts(team))
    if issues:
        # The veto checks below divide by counts that only make sense once the role counts
        # are in range; reporting both at once would produce noise.
        return issues
    issues.extend(_check_vetoes(team, config))
    return issues


def _check_role_counts(team: Team) -> list[FeasibilityIssue]:
    """Section 7 arithmetic, per role, generalised from 8 to ``team.n_positions``."""
    issues: list[FeasibilityIssue] = []
    p = team.n_positions
    for role in Role:
        dancers = team.by_role(role)
        n = len(dancers)
        role_de = _ROLE_DE[role]

        if not p <= n <= 2 * p:
            issues.append(
                _issue(
                    "ROLE_COUNT_OUT_OF_RANGE",
                    tuple(d.id for d in dancers),
                    role_de=role_de,
                    n=n,
                    p=p,
                    max_n=2 * p,
                )
            )
            continue

        singles = team.n_single_positions(role)
        startanspruch = [d for d in dancers if d.has_startanspruch]
        if len(startanspruch) > singles:
            issues.append(
                _issue(
                    "TOO_MANY_STARTANSPRUCH",
                    tuple(d.id for d in startanspruch),
                    role_de=role_de,
                    count=len(startanspruch),
                    available=singles,
                    n=n,
                    p=p,
                )
            )

        doubled = team.n_doubled_positions(role)
        coaching = [d for d in dancers if d.needs_coaching]
        needed = ceil_div(len(coaching), 2) if coaching else 0
        if needed > doubled:
            issues.append(
                _issue(
                    "TOO_MANY_COACHING",
                    tuple(d.id for d in coaching),
                    role_de=role_de,
                    count=len(coaching),
                    needed=needed,
                    available=doubled,
                    n=n,
                    p=p,
                )
            )
    return issues


def _check_vetoes(team: Team, config: SolverConfig) -> list[FeasibilityIssue]:
    """Hard vetoes that make a role infeasible by counting alone."""
    issues: list[FeasibilityIssue] = []
    vetoes = veto_pairs(team, config)
    if not vetoes:
        return issues

    def is_vetoed(a: str, b: str) -> bool:
        return frozenset((a, b)) in vetoes

    for dancer in team.dancers:
        opposite = team.by_role(dancer.role.opposite)
        if opposite and all(is_vetoed(dancer.id, other.id) for other in opposite):
            issues.append(
                _issue(
                    "VETO_ALL_CROSS_ROLE",
                    (dancer.id,),
                    name=dancer.name,
                    opposite_de=_ROLE_DE[dancer.role.opposite],
                )
            )

    for role in Role:
        dancers = team.by_role(role)
        singles = team.n_single_positions(role)
        forced_single: list[str] = []
        for dancer in dancers:
            same_role_others = [other for other in dancers if other.id != dancer.id]
            admissible = [other for other in same_role_others if not is_vetoed(dancer.id, other.id)]
            if dancer.has_startanspruch:
                forced_single.append(dancer.id)
            elif not admissible:
                if dancer.needs_coaching:
                    issues.append(
                        _issue(
                            "VETO_COACHING_ISOLATED",
                            (dancer.id,),
                            name=dancer.name,
                            role_de=_ROLE_DE[role],
                        )
                    )
                forced_single.append(dancer.id)

        if len(forced_single) > singles:
            issues.append(
                _issue(
                    "VETO_FORCES_SINGLES",
                    tuple(forced_single),
                    role_de=_ROLE_DE[role],
                    count=len(forced_single),
                    available=singles,
                )
            )
    return issues
