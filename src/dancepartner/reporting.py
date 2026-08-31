"""Pure derivations of the numbers a report shows, shared by the CLI and the Streamlit UI.

Nothing here renders. Every function takes a solved :class:`~dancepartner.scoring.Solution` and
returns plain data, so the CLI can ``echo`` it and the UI can put it in a widget without either
of them re-deriving it. The two surfaces disagreeing about what "unfulfilled" means would be a
bug the test suite could not see, because each would be self-consistent.

No ``streamlit``, no ``typer``: this module sits between ``scoring`` and ``cli``/the UI.
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict

from .model import SolverConfig, Team, WeightScheme
from .scoring import DancerSatisfaction, Solution, build_weights, geometric_base, tier_weight

__all__ = [
    "MAX_LISTED_VARIANTS",
    "ExchangeGroup",
    "GroupVariant",
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


MAX_LISTED_VARIANTS = 5
"""Above this many constellations the surfaces list per-dancer position options instead --
fifty variant lines answer nothing a coach asks. Shared here so CLI and UI agree."""


class GroupVariant(BaseModel):
    """One constellation an exchange group can take.

    Attributes:
        solution_indices: 0-based indices into the **full** shortlist that realise this
            constellation, ascending -- ``index + 1`` is the "solution n" both surfaces print.
        labels: Dancer id -> position label under this constellation.
    """

    model_config = ConfigDict(frozen=True)

    solution_indices: list[int]
    labels: dict[str, str]


class ExchangeGroup(BaseModel):
    """Dancers the coach can swap between equally good solutions.

    "Equally good" means the sorted per-dancer score vector is identical to the best
    solution's -- applying another variant of the group makes nobody worse off, individually
    or in total. Movement is by position label, the same notion as :func:`moved_dancers`:
    the partners a mover joins or leaves are not part of the group.

    Attributes:
        number: 1-based, deterministic -- group 1 touches the alphabetically first position.
        dancer_ids: The movers, sorted by (best-solution label, id).
        variants: The distinct constellations; ``variants[0]`` is the best solution's.
    """

    model_config = ConfigDict(frozen=True)

    number: int
    dancer_ids: list[str]
    variants: list[GroupVariant]


def exchange_groups(solutions: Sequence[Solution]) -> list[ExchangeGroup]:
    """The exchange groups across a shortlist; empty without at least two equal solutions.

    Only solutions whose sorted score vector matches ``solutions[0]``'s take part -- a
    near-optimal entry stays browsable in the shortlist but never suggests a swap that would
    make the team unhappier. Within one peer solution, movers whose from/to labels touch a
    common position form one group (a permutation cycle chains labels); groups sharing a
    dancer across peers are merged.
    """
    if len(solutions) < 2:
        return []
    best_places = positions_by_dancer(solutions[0])
    best_vector = sorted(s.score for s in solutions[0].per_dancer.values())
    peers = [
        (index, solution)
        for index, solution in enumerate(solutions)
        if sorted(s.score for s in solution.per_dancer.values()) == best_vector
    ]
    if len(peers) < 2:
        return []

    parent: dict[str, str] = {}

    def find(dancer: str) -> str:
        root = dancer
        while parent[root] != root:
            root = parent[root]
        while parent[dancer] != root:
            parent[dancer], dancer = root, parent[dancer]
        return root

    def union(a: str, b: str) -> None:
        root_a, root_b = find(a), find(b)
        if root_a != root_b:
            parent[root_b] = root_a

    peer_places: dict[int, dict[str, str]] = {}
    for index, solution in peers:
        places = positions_by_dancer(solution)
        peer_places[index] = places
        # Movers whose from/to labels touch a common position change that position's
        # constellation jointly, so they union into one group.
        anchor_by_label: dict[str, str] = {}
        for dancer in sorted(d for d, label in places.items() if label != best_places[d]):
            parent.setdefault(dancer, dancer)
            for label in (best_places[dancer], places[dancer]):
                if label in anchor_by_label:
                    union(anchor_by_label[label], dancer)
                else:
                    anchor_by_label[label] = dancer

    members: dict[str, list[str]] = {}
    for dancer in parent:
        members.setdefault(find(dancer), []).append(dancer)

    unnumbered: list[tuple[list[str], list[GroupVariant]]] = []
    for ids in members.values():
        ordered_ids = sorted(ids, key=lambda d: (best_places[d], d))
        seen: dict[tuple[tuple[str, str], ...], list[int]] = {}
        for index, _ in peers:
            key = tuple((d, peer_places[index][d]) for d in ordered_ids)
            seen.setdefault(key, []).append(index)
        # Peers arrive in shortlist order and the best solution is always a peer, so the
        # first key is the best constellation and the rest sort by first appearance.
        variants = [
            GroupVariant(solution_indices=indices, labels=dict(key))
            for key, indices in seen.items()
        ]
        unnumbered.append((ordered_ids, variants))

    unnumbered.sort(key=lambda item: min((best_places[d], d) for d in item[0]))
    return [
        ExchangeGroup(number=number, dancer_ids=ids, variants=variants)
        for number, (ids, variants) in enumerate(unnumbered, start=1)
    ]


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
