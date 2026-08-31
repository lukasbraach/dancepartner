"""Pure derivations of the numbers a report shows, shared by the CLI and the Streamlit UI.

Nothing here renders. Every function takes a solved :class:`~dancepartner.scoring.Solution` and
returns plain data, so the CLI can ``echo`` it and the UI can put it in a widget without either
of them re-deriving it. The two surfaces disagreeing about what "unfulfilled" means would be a
bug the test suite could not see, because each would be self-consistent.

No ``streamlit``, no ``typer``: this module sits between ``scoring`` and ``cli``/the UI.
"""

from __future__ import annotations

from collections.abc import Sequence
from itertools import permutations

from pydantic import BaseModel, ConfigDict

from .feasibility import veto_pairs
from .model import Role, SolverConfig, Team, WeightScheme
from .scoring import (
    DancerSatisfaction,
    Solution,
    build_satisfaction,
    build_weights,
    geometric_base,
    tier_weight,
)

__all__ = [
    "MAX_GROUP_SIZE",
    "ExchangeGroup",
    "exchange_groups",
    "group_numbers",
    "moved_dancers",
    "positions_by_dancer",
    "respected_not_desired",
    "satisfaction_ratio",
    "satisfaction_rows",
    "unfulfilled_desired",
]


def positions_by_dancer(solution: Solution) -> dict[str, str]:
    """Map every dancer id to the label (A-H) of the position they sit on."""
    return {
        dancer_id: position.label
        for position in solution.positions
        for dancer_id in (*position.leaders, *position.followers)
    }


def satisfaction_rows(solution: Solution, team: Team) -> list[tuple[str, str, DancerSatisfaction]]:
    """Return ``(dancer_id, name, satisfaction)`` sorted by ascending score, then id.

    Ascending is not a stylistic choice: the unhappiest dancer is the row the coach actually
    needs, so it goes first (SPEC.md 10).
    """
    by_id = team.dancers_by_id
    ordered = sorted(solution.per_dancer.items(), key=lambda item: (item[1].score, item[0]))
    return [(dancer_id, by_id[dancer_id].name, sat) for dancer_id, sat in ordered]


def unfulfilled_desired(
    team: Team, dancer_id: str, satisfaction: DancerSatisfaction
) -> dict[int, list[str]]:
    """Tier rank -> wished-for partners this dancer did *not* get, empty tiers dropped.

    Unlike :func:`respected_not_desired` this does not filter by
    :attr:`SolverConfig.scope`: a wish the coach wrote down stays a wish they can see was
    missed, even when the objective never scored it.
    """
    survey = team.surveys_by_id.get(dancer_id)
    if survey is None:
        return {}
    granted = {i for ids in satisfaction.fulfilled_desired.values() for i in ids}
    missed = {
        tier.rank: sorted(i for i in tier.dancer_ids if i not in granted)
        for tier in survey.desired_tiers
    }
    return {rank: ids for rank, ids in missed.items() if ids}


def respected_not_desired(
    team: Team, config: SolverConfig, dancer_id: str, satisfaction: DancerSatisfaction
) -> dict[int, list[str]]:
    """Tier rank -> disliked dancers this dancer was kept away from, empty tiers dropped.

    Filtered by ``config.scope``: claiming credit for keeping two leaders apart under
    CROSS_ROLE_ONLY would be claiming credit for a constraint nothing enforced.
    """
    survey = team.surveys_by_id.get(dancer_id)
    if survey is None:
        return {}
    violated = {i for ids in satisfaction.violated_not_desired.values() for i in ids}
    respected = {
        tier.rank: sorted(
            i
            for i in tier.dancer_ids
            if i not in violated and team.in_scope(dancer_id, i, config.scope)
        )
        for tier in survey.not_desired_tiers
    }
    return {rank: ids for rank, ids in respected.items() if ids}


def satisfaction_ratio(
    team: Team, config: SolverConfig, dancer_id: str, satisfaction: DancerSatisfaction
) -> float | None:
    """One dancer's satisfaction as a fraction of their attainable maximum, or ``None``.

    Only meaningful under ``ScoreAggregation.BEST``, where the positive part of a score
    saturates at the instance-global top-tier weight: a fulfilled tier-1 wish with no violated
    dislike is exactly ``1.0`` for every dancer, single or doubled. Violations pull the value
    below that, possibly under zero. A dancer whose survey holds only dislikes starts at
    ``1.0`` and loses from there. ``None`` means the dancer stated no in-scope preference at
    all -- neutral, not unhappy -- and the UI shows them without a colour.
    """
    weights = build_weights(team, config)
    own = [weight for (source, _), weight in weights.items() if source == dancer_id]
    if not own:
        return None
    base = geometric_base(team, config) if config.weights is WeightScheme.GEOMETRIC else None
    top = tier_weight(1, "desired", team.max_rank, base) * config.score_scale
    if any(weight > 0 for weight in own):
        return satisfaction.score / top
    return 1.0 + satisfaction.score / top


MAX_GROUP_SIZE = 8
"""Cap on the members of one exchange group. Free interchangeability is verified against
every permutation of the group, and 8! is where exhaustive checking stays instant."""


class ExchangeGroup(BaseModel):
    """Dancers who can be rearranged freely within one solution at zero cost.

    Every permutation of the group's dancers over their positions keeps every hard
    constraint and the solution's sorted per-dancer score vector -- the coach can shuffle
    them in any order and nobody ends up worse, individually or in total. Three dancers form
    a group of three only when **all six** arrangements hold: interchangeability is not
    transitive, so it is verified against full permutation closure, never chained.

    Groups are role-pure by physics, not by fiat: a cross-role permutation would change a
    position's role counts and can therefore never be equivalent.

    Attributes:
        number: 1-based, deterministic -- group 1 holds the alphabetically first position.
        role: The shared role of every dancer in the group.
        dancer_ids: Sorted by (position label, id).
        labels: Dancer id -> the position label they hold in the examined solution.
    """

    model_config = ConfigDict(frozen=True)

    number: int
    role: Role
    dancer_ids: list[str]
    labels: dict[str, str]


def exchange_groups(solution: Solution, team: Team, config: SolverConfig) -> list[ExchangeGroup]:
    """The maximal freely-interchangeable dancer sets of ``solution``.

    Permuted assignments are re-validated and re-scored directly (via
    :func:`~dancepartner.scoring.build_satisfaction`), so the groups depend only on the
    solution being shown -- never on which other solutions the enumeration pass happened to
    return before its cap. Grown greedily in (label, id) order and verified against full
    permutation closure on every extension; a dancer belongs to at most one group.
    Co-positioned dancers are never grouped: their "swap" changes nothing.
    """
    by_id = team.dancers_by_id
    places = positions_by_dancer(solution)
    base_vector = sorted(s.score for s in solution.per_dancer.values())
    base_groups = {p.label: [*p.leaders, *p.followers] for p in solution.positions}
    label_order = [p.label for p in solution.positions]
    vetoes = veto_pairs(team, config)

    def position_ok(occupants: list[str]) -> bool:
        """Hard constraints that a same-role permutation can still break on one position."""
        for role in Role:
            role_members = [i for i in occupants if by_id[i].role is role]
            if len(role_members) == 1 and by_id[role_members[0]].needs_coaching:
                return False
            if len(role_members) == 2:
                if any(by_id[i].is_pole_position for i in role_members):
                    return False
                if all(by_id[i].needs_coaching for i in role_members):
                    return False
        return not any(frozenset((a, b)) in vetoes for a in occupants for b in occupants if a < b)

    def base_slot(dancer: str) -> tuple[int, ...]:
        return tuple(sorted(solution.per_dancer[i].score for i in base_groups[places[dancer]]))

    # slot_scores[(mover, displaced)]: the scores the displaced dancer's position takes when
    # the mover stands there instead. Scores are position-local and within a group every
    # position holds exactly one member, so the value holds in *any* permutation sending the
    # mover to that member's place. None marks a transposition that broke a hard constraint
    # or the sorted score vector.
    slot_scores: dict[tuple[str, str], tuple[int, ...] | None] = {}

    def evaluate_swap(d: str, e: str) -> None:
        """Score the transposition of ``d`` and ``e``, filling both slot_scores entries."""
        if (d, e) in slot_scores:
            return
        permuted = {
            label: [d if i == e else e if i == d else i for i in occupants]
            for label, occupants in base_groups.items()
        }
        if not (position_ok(permuted[places[d]]) and position_ok(permuted[places[e]])):
            slot_scores[(d, e)] = slot_scores[(e, d)] = None
            return
        satisfaction = build_satisfaction(team, config, [permuted[label] for label in label_order])
        if sorted(s.score for s in satisfaction.values()) != base_vector:
            slot_scores[(d, e)] = slot_scores[(e, d)] = None
            return
        slot_scores[(d, e)] = tuple(sorted(satisfaction[i].score for i in permuted[places[e]]))
        slot_scores[(e, d)] = tuple(sorted(satisfaction[i].score for i in permuted[places[d]]))

    def closed(members: list[str]) -> bool:
        """Whether every permutation of ``members`` preserves the sorted score vector.

        Positions outside the members' places never change, so only the members' positions'
        score multisets are compared -- against the identity arrangement.
        """
        identity = sorted(score for m in members for score in base_slot(m))
        for arrangement in permutations(members):
            combined: list[int] = []
            for mover, displaced in zip(arrangement, members, strict=True):
                if mover == displaced:
                    combined.extend(base_slot(displaced))
                    continue
                scores = slot_scores[(mover, displaced)]
                assert scores is not None  # the pairwise pre-check filtered invalid swaps
                combined.extend(scores)
            if sorted(combined) != identity:
                return False
        return True

    order = sorted(places, key=lambda i: (places[i], i))
    assigned: set[str] = set()
    groups: list[ExchangeGroup] = []
    for seed in order:
        if seed in assigned:
            continue
        members = [seed]
        used_positions = {places[seed]}
        for candidate in order:
            if len(members) >= MAX_GROUP_SIZE:
                break
            if (
                candidate in assigned
                or candidate in members
                or by_id[candidate].role is not by_id[seed].role
                or places[candidate] in used_positions
            ):
                continue
            for member in members:
                evaluate_swap(member, candidate)
            if any(slot_scores[(candidate, member)] is None for member in members) or not closed(
                [*members, candidate]
            ):
                continue
            members.append(candidate)
            used_positions.add(places[candidate])
        if len(members) > 1:
            assigned.update(members)
            groups.append(
                ExchangeGroup(
                    number=len(groups) + 1,
                    role=by_id[seed].role,
                    dancer_ids=members,
                    labels={m: places[m] for m in members},
                )
            )
    return groups


def group_numbers(groups: Sequence[ExchangeGroup]) -> dict[str, int]:
    """Map every dancer in any exchange group to their group's number."""
    return {dancer: group.number for group in groups for dancer in group.dancer_ids}


def moved_dancers(
    reference: Solution, solution: Solution, team: Team
) -> list[tuple[str, str, str]]:
    """``(name, from_label, to_label)`` for every dancer who sits elsewhere than in ``reference``.

    Sorted by name. Never empty for two distinct shortlist entries: the shortlist is
    deduplicated by ``Solution.signature``, so two entries always differ in who sits with whom,
    not merely in which label a group carries.
    """
    before = positions_by_dancer(reference)
    after = positions_by_dancer(solution)
    by_id = team.dancers_by_id
    return [
        (by_id[dancer_id].name, before[dancer_id], after[dancer_id])
        for dancer_id in sorted(after, key=lambda i: by_id[i].name)
        if before[dancer_id] != after[dancer_id]
    ]
