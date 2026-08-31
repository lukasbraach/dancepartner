"""Weight schemes, result types, and per-dancer satisfaction reporting.

Integer arithmetic only. Everything the solver optimises is an ``int``; see
``SolverConfig.score_scale`` for the factor that lets a halved score stay integral.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from pydantic import BaseModel, ConfigDict, Field

from .feasibility import veto_pairs
from .model import (
    Direction,
    PreferenceScope,
    Role,
    SolverConfig,
    Team,
    WeightScheme,
    position_labels,
)

__all__ = [
    "DancerSatisfaction",
    "PositionAssignment",
    "Solution",
    "build_satisfaction",
    "build_solution",
    "build_weights",
    "geometric_base",
    "scored_pairs",
    "tier_weight",
]


class PositionAssignment(BaseModel):
    """The dancers on one position. ``label`` is A-H, never a number."""

    model_config = ConfigDict(frozen=True)

    label: str
    leaders: list[str]
    followers: list[str]

    @property
    def is_doubled(self) -> bool:
        """A *Doppelbesetzung* in the strict sense: two leaders **and** two followers."""
        return len(self.leaders) == 2 and len(self.followers) == 2

    def role_ids(self, role: Role) -> list[str]:
        """Dancer ids of one role on this position."""
        return self.leaders if role is Role.LEADER else self.followers


class DancerSatisfaction(BaseModel):
    """What one dancer got out of an assignment.

    Attributes:
        score: The dancer's objective contribution, on the solver's integer scale. With
            ``SolverConfig.normalize_double`` that scale is x2, so a value of 6 with a
            LINEAR tier weight of 3 means one fulfilled top wish, not six of anything.
        fulfilled_desired: Tier rank -> the wished-for partner ids actually granted.
        violated_not_desired: Tier rank -> the un-wished partner ids co-positioned anyway.
        neutral_partners: In-scope co-positioned dancers this dancer named in no tier.
    """

    model_config = ConfigDict(frozen=True)

    score: int
    fulfilled_desired: dict[int, list[str]] = Field(default_factory=dict)
    violated_not_desired: dict[int, list[str]] = Field(default_factory=dict)
    neutral_partners: list[str] = Field(default_factory=list)


class Solution(BaseModel):
    """One complete *Verpartnerung*.

    ``total_score`` and ``min_score`` are on the same scale as ``DancerSatisfaction.score``.
    """

    model_config = ConfigDict(frozen=True)

    positions: list[PositionAssignment]
    total_score: int
    min_score: int
    per_dancer: dict[str, DancerSatisfaction]

    @property
    def signature(self) -> frozenset[frozenset[str]]:
        """Canonical identity of the assignment, ignoring position labels.

        Symmetry breaking makes positions comparable, but the frozenset of frozensets is the
        honest key: two solutions that differ only in which label a group carries are the
        same *Verpartnerung*.
        """
        return frozenset(
            frozenset((*position.leaders, *position.followers)) for position in self.positions
        )


def geometric_base(team: Team, config: SolverConfig) -> int:
    """Smallest base ``B`` for which one tier-*k* fulfilment outranks every tier-*(k+1)* one.

    A dancer can be co-positioned with at most two opposite-role dancers, plus one same-role
    dancer under ``PreferenceScope.ALL``. So the whole team can fulfil at most
    ``max_per_dancer * n_dancers`` entries of any single tier, and ``B`` one greater than that
    dominates them all.

    Warning:
        Geometric weights blow up the objective's coefficient range, which degrades CP-SAT's
        bound quality and therefore its ability to prove optimality on larger instances.
        ``WeightScheme.LINEAR`` is the safer default; reach for GEOMETRIC only when tier
        ordering must be strict.
    """
    max_per_dancer = 3 if config.scope is PreferenceScope.ALL else 2
    return max_per_dancer * max(len(team.dancers), 1) + 1


def tier_weight(rank: int, direction: Direction, max_rank: int, base: int | None) -> int:
    """Weight of a single tier entry.

    Args:
        rank: The tier rank, 1 being strongest.
        direction: ``"desired"`` gives a positive weight, ``"not_desired"`` a negative one of
            the same magnitude -- dislikes are symmetric to likes.
        max_rank: ``K``, the largest rank in the instance. Instance-global rather than
            per-dancer, so a dancer who listed one tier is not scored lower than one who
            listed three.
        base: ``B`` for GEOMETRIC weights, ``None`` for LINEAR.
    """
    magnitude = max_rank - rank + 1 if base is None else base ** (max_rank - rank)
    return magnitude if direction == "desired" else -magnitude


def build_weights(team: Team, config: SolverConfig) -> dict[tuple[str, str], int]:
    """Map every directed, in-scope survey entry to its integer weight.

    The key is ordered ``(source, target)``: preferences are directed and the two directions
    of a pair are scored independently.
    """
    max_rank = team.max_rank
    base = geometric_base(team, config) if config.weights is WeightScheme.GEOMETRIC else None
    weights: dict[tuple[str, str], int] = {}
    for entry in team.preference_entries(config.scope):
        weights[(entry.source, entry.target)] = tier_weight(
            entry.rank, entry.direction, max_rank, base
        )
    return weights


def scored_pairs(team: Team, config: SolverConfig) -> list[frozenset[str]]:
    """Unordered pairs that need a reified ``together`` variable.

    Only pairs carrying a non-zero weight in either direction, or a hard veto, can change the
    objective or the feasible set. Everyone else is neutral to everyone else, and a variable
    for them would be several hundred useless booleans on a realistic roster.
    """
    pairs: set[frozenset[str]] = set()
    for source, target in build_weights(team, config):
        pairs.add(frozenset((source, target)))
    # Vetoes are already in build_weights (a vetoed pair is always a not_desired entry), but
    # deriving them separately keeps this correct if veto handling ever widens.
    pairs |= veto_pairs(team, config)
    return sorted(pairs, key=lambda pair: sorted(pair))


def _partners_of(
    dancer_id: str, group: Iterable[str], team: Team, scope: PreferenceScope
) -> list[str]:
    return sorted(other for other in group if team.in_scope(dancer_id, other, scope))


def build_satisfaction(
    team: Team, config: SolverConfig, groups: Sequence[Sequence[str]]
) -> dict[str, DancerSatisfaction]:
    """Recompute every dancer's satisfaction from a concrete assignment.

    Args:
        team: The instance.
        config: Weight scheme, scope and normalisation to apply.
        groups: One sequence of dancer ids per position.

    This is deliberately independent of the CP-SAT model: the tests use it to check that the
    solver modelled what we think it modelled, so it must not share code with the model
    construction.
    """
    weights = build_weights(team, config)
    surveys = team.surveys_by_id
    by_id = team.dancers_by_id
    scale = config.score_scale

    result: dict[str, DancerSatisfaction] = {}
    for group in groups:
        for dancer_id in group:
            dancer = by_id[dancer_id]
            partners = _partners_of(dancer_id, group, team, config.scope)
            n_cross = sum(1 for other in group if by_id[other].role is not dancer.role)

            score = 0
            fulfilled: dict[int, list[str]] = {}
            violated: dict[int, list[str]] = {}
            neutral: list[str] = []
            survey = surveys.get(dancer_id)
            for other in partners:
                weight = weights.get((dancer_id, other), 0)
                cross_role = by_id[other].role is not dancer.role
                # A dancer on a Doppelbesetzung of the opposite role has two cross-role
                # partners and would otherwise collect twice the contributions. Halve those,
                # working on the x2 scale so nothing rounds.
                if config.normalize_double and cross_role and n_cross == 2:
                    score += weight
                else:
                    score += weight * scale

                rank = survey.rank_of(other, "desired") if survey else None
                if rank is not None:
                    fulfilled.setdefault(rank, []).append(other)
                    continue
                rank = survey.rank_of(other, "not_desired") if survey else None
                if rank is not None:
                    violated.setdefault(rank, []).append(other)
                else:
                    neutral.append(other)

            result[dancer_id] = DancerSatisfaction(
                score=score,
                fulfilled_desired={rank: sorted(ids) for rank, ids in sorted(fulfilled.items())},
                violated_not_desired={rank: sorted(ids) for rank, ids in sorted(violated.items())},
                neutral_partners=neutral,
            )
    return result


def build_solution(team: Team, config: SolverConfig, groups: Sequence[Sequence[str]]) -> Solution:
    """Assemble a :class:`Solution` from one dancer id group per position."""
    by_id = team.dancers_by_id
    labels = position_labels(len(groups))
    positions = [
        PositionAssignment(
            label=label,
            leaders=sorted(i for i in group if by_id[i].role is Role.LEADER),
            followers=sorted(i for i in group if by_id[i].role is Role.FOLLOWER),
        )
        for label, group in zip(labels, groups, strict=True)
    ]
    per_dancer = build_satisfaction(team, config, groups)
    scores = [satisfaction.score for satisfaction in per_dancer.values()]
    return Solution(
        positions=positions,
        total_score=sum(scores),
        min_score=min(scores, default=0),
        per_dancer=per_dancer,
    )
