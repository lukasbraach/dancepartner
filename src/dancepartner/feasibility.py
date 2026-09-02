"""Cheap counting pre-checks, run before the CP-SAT model is built.

The solver must never answer a question that arithmetic already settles: a bare INFEASIBLE
tells the coach nothing, while "5 leaders hold a pole position but only 4 positions carry a
single leader" tells them exactly which flag to change.

Diagnostics live in :mod:`dancepartner.i18n`, keyed ``feasibility.<code>``, and render in the
language active when the check runs.

These checks are **necessary, not sufficient**. Passing them does not prove the instance is
solvable; CP-SAT remains the authority on infeasibility. Every check here is a pure counting
argument, so a reported issue is always a real one.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from .i18n import t
from .model import Role, SolverConfig, Team

__all__ = ["FeasibilityIssue", "check_feasibility", "together_components", "veto_pairs"]


def _role_plural(role: Role) -> str:
    """Plural label for ``role`` in the active language."""
    return t(f"role.{role.value}.plural")


class FeasibilityIssue(BaseModel):
    """One decidable-by-counting reason the instance cannot be solved.

    Attributes:
        code: Stable machine-readable identifier, English.
        message: Explanation for the coach, rendered in the language active at construction.
            Never store issues across a language switch — the UI recomputes them each run.
        involved_ids: Dancer ids the issue is about; empty when it is purely about counts.
    """

    model_config = ConfigDict(frozen=True)

    code: str
    message: str
    involved_ids: tuple[str, ...] = ()


def _issue(code: str, involved_ids: tuple[str, ...] = (), **params: object) -> FeasibilityIssue:
    return FeasibilityIssue(
        code=code, message=t(f"feasibility.{code}", **params), involved_ids=involved_ids
    )


def veto_pairs(team: Team, config: SolverConfig) -> set[frozenset[str]]:
    """Unordered dancer pairs that must not share a position.

    A veto is symmetric even though preferences are not: if A vetoes B at the configured
    tier, the pair cannot share a position, whatever B wrote about A.
    """
    pairs: set[frozenset[str]] = set()
    for entry in team.preference_entries(config.scope):
        if entry.direction == "not_desired" and config.vetoed_ranks(entry.rank):
            pairs.add(frozenset((entry.source, entry.target)))
    return pairs


def together_components(team: Team) -> list[frozenset[str]]:
    """The coach's ``together`` groups, merged over shared members.

    ``{a, b}`` and ``{b, c}`` both on one position means all three are, so the groups the
    solver and the checks below have to honour are the connected components of the groups,
    not the groups as written. Single source of truth for that closure, the way
    :func:`veto_pairs` is for vetoes: the two backends, :mod:`dancepartner.reporting` and the
    tests must not be able to disagree about it.

    Returns them sorted, so everything downstream is deterministic.
    """
    components: list[set[str]] = []
    for group in team.coach_constraints.together:
        merged = set(group)
        rest: list[set[str]] = []
        for component in components:
            if component & merged:
                merged |= component
            else:
                rest.append(component)
        rest.append(merged)
        components = rest
    return sorted((frozenset(c) for c in components), key=lambda c: sorted(c))


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
    issues.extend(_check_coach_constraints(team, config))
    return issues


def _check_role_counts(team: Team) -> list[FeasibilityIssue]:
    """Section 7 arithmetic, per role, generalised from 8 to ``team.n_positions``."""
    issues: list[FeasibilityIssue] = []
    p = team.n_positions
    for role in Role:
        dancers = team.by_role(role)
        n = len(dancers)
        role_label = _role_plural(role)

        if not p <= n <= 2 * p:
            issues.append(
                _issue(
                    "ROLE_COUNT_OUT_OF_RANGE",
                    tuple(d.id for d in dancers),
                    role_label=role_label,
                    n=n,
                    p=p,
                    max_n=2 * p,
                )
            )
            continue

        singles = team.n_single_positions(role)
        pole_position = [d for d in dancers if d.is_pole_position]
        if len(pole_position) > singles:
            issues.append(
                _issue(
                    "TOO_MANY_POLE_POSITION",
                    tuple(d.id for d in pole_position),
                    role_label=role_label,
                    count=len(pole_position),
                    available=singles,
                    n=n,
                    p=p,
                )
            )

        doubled = team.n_doubled_positions(role)
        coaching = [d for d in dancers if d.needs_coaching]
        # Two coaching dancers must never share a position, so each needs their own doubled
        # position with an experienced same-role partner.
        if len(coaching) > doubled:
            issues.append(
                _issue(
                    "TOO_MANY_COACHING",
                    tuple(d.id for d in coaching),
                    role_label=role_label,
                    count=len(coaching),
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
                    opposite_label=_role_plural(dancer.role.opposite),
                )
            )

    for role in Role:
        dancers = team.by_role(role)
        singles = team.n_single_positions(role)
        forced_single: list[str] = []
        for dancer in dancers:
            same_role_others = [other for other in dancers if other.id != dancer.id]
            admissible = [other for other in same_role_others if not is_vetoed(dancer.id, other.id)]
            if dancer.needs_coaching:
                # The same-role partner of a coaching dancer must be experienced.
                admissible = [other for other in admissible if not other.needs_coaching]
            if dancer.is_pole_position:
                forced_single.append(dancer.id)
            elif not admissible:
                if dancer.needs_coaching:
                    issues.append(
                        _issue(
                            "VETO_COACHING_ISOLATED",
                            (dancer.id,),
                            name=dancer.name,
                            role_label=_role_plural(role),
                        )
                    )
                forced_single.append(dancer.id)

        if len(forced_single) > singles:
            issues.append(
                _issue(
                    "VETO_FORCES_SINGLES",
                    tuple(forced_single),
                    role_label=_role_plural(role),
                    count=len(forced_single),
                    available=singles,
                )
            )
    return issues


def _names(team: Team, ids: frozenset[str] | tuple[str, ...]) -> str:
    """Display names for a set of ids, in roster order, for a diagnostic message."""
    return ", ".join(dancer.name for dancer in team.dancers if dancer.id in ids)


def _check_coach_constraints(team: Team, config: SolverConfig) -> list[FeasibilityIssue]:
    """The coach's own hard rules (SPEC.md 8, 7.), where counting alone already refuses them.

    Every check here is about one position's capacity or the pigeonhole principle, so a
    reported issue is a real obstruction -- the module's standing promise. Whether the rules
    are *jointly* satisfiable with everybody else's remains the solver's question.
    """
    issues: list[FeasibilityIssue] = []
    components = together_components(team)
    if not components and not team.coach_constraints.apart:
        return issues

    by_id = team.dancers_by_id
    vetoes = veto_pairs(team, config)
    needs_double: dict[Role, list[frozenset[str]]] = {role: [] for role in Role}

    for component in components:
        for role in Role:
            members = [i for i in sorted(component) if by_id[i].role is role]
            if len(members) > 2:
                issues.append(
                    _issue(
                        "COACH_TOGETHER_TOO_MANY_OF_ROLE",
                        tuple(members),
                        names=_names(team, component),
                        role_label=_role_plural(role),
                        count=len(members),
                    )
                )
                continue
            if len(members) < 2:
                continue
            # Two of a role on one position *is* a doubled position for that role.
            needs_double[role].append(component)
            pole = [i for i in members if by_id[i].is_pole_position]
            if pole:
                issues.append(
                    _issue(
                        "COACH_TOGETHER_POLE_POSITION",
                        tuple(members),
                        name=by_id[pole[0]].name,
                        other=by_id[next(i for i in members if i not in pole)].name,
                    )
                )
            if all(by_id[i].needs_coaching for i in members):
                issues.append(
                    _issue(
                        "COACH_TOGETHER_TWO_COACHING",
                        tuple(members),
                        names=_names(team, frozenset(members)),
                        role_label=_role_plural(role),
                    )
                )

        vetoed = sorted(pair for pair in vetoes if pair <= component)
        for pair in vetoed:
            issues.append(
                _issue(
                    "COACH_TOGETHER_VETO",
                    tuple(sorted(pair)),
                    names=_names(team, pair),
                )
            )

    # The components are disjoint by construction, so each one that needs a doubled position
    # for a role consumes a distinct one; counting them against the supply is exact.
    for role in Role:
        available = team.n_doubled_positions(role)
        wanted = needs_double[role]
        if len(wanted) > available:
            issues.append(
                _issue(
                    "COACH_TOGETHER_NEEDS_DOUBLES",
                    tuple(sorted(frozenset().union(*wanted))),
                    role_label=_role_plural(role),
                    count=len(wanted),
                    available=available,
                )
            )

    for group in team.coach_constraints.apart:
        if len(group) > team.n_positions:
            issues.append(
                _issue(
                    "COACH_APART_TOO_MANY",
                    tuple(sorted(group)),
                    names=_names(team, group),
                    count=len(group),
                    p=team.n_positions,
                )
            )
        for component in components:
            both = group & component
            if len(both) > 1:
                issues.append(
                    _issue(
                        "COACH_TOGETHER_AND_APART",
                        tuple(sorted(both)),
                        names=_names(team, both),
                    )
                )
    return issues
