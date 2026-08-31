"""Pure derivations of the numbers a report shows, shared by the CLI and the Streamlit UI.

Nothing here renders. Every function takes a solved :class:`~dancepartner.scoring.Solution` and
returns plain data, so the CLI can ``echo`` it and the UI can put it in a widget without either
of them re-deriving it. The two surfaces disagreeing about what "unfulfilled" means would be a
bug the test suite could not see, because each would be self-consistent.

No ``streamlit``, no ``typer``: this module sits between ``scoring`` and ``cli``/the UI.
"""

from __future__ import annotations

from .model import SolverConfig, Team, WeightScheme
from .scoring import DancerSatisfaction, Solution, build_weights, geometric_base, tier_weight

__all__ = [
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
