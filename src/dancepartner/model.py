"""Domain model for the formation team assignment problem.

Identifiers are English throughout (SPEC.md 2). Where a name replaces a German term of art
the team used to say, the docstring records the old word so the transition stays traceable:
``is_pole_position`` was *Startanspruch*, ``needs_coaching`` was *Coachingbedarf*,
``desired_tiers`` were *Wunschpartner*, ``is_doubled`` is a *Doppelbesetzung*. User-facing
output is bilingual and lives in :mod:`dancepartner.i18n`.
"""

from __future__ import annotations

from collections.abc import Iterator
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

__all__ = [
    "DEFAULT_N_POSITIONS",
    "Dancer",
    "Direction",
    "Objective",
    "PreferenceScope",
    "PreferenceEntry",
    "Role",
    "ScoreAggregation",
    "SolverConfig",
    "Survey",
    "Team",
    "Tier",
    "position_label",
    "position_labels",
]

DEFAULT_N_POSITIONS = 8

Direction = Literal["desired", "not_desired"]
"""Which of the two preference directions an entry belongs to."""


class Role(StrEnum):
    """The two dance roles. Fixed per dancer, never a preference.

    ``LEADER`` is the leading role, ``FOLLOWER`` the following role.
    """

    LEADER = "leader"
    FOLLOWER = "follower"

    @property
    def opposite(self) -> Role:
        """The other role."""
        return Role.FOLLOWER if self is Role.LEADER else Role.LEADER


class PreferenceScope(StrEnum):
    """Which dancer pairs a preference may be expressed about.

    ``CROSS_ROLE_ONLY``: only leader-follower pairs are scored, the narrow reading of the
    survey (a leader names followers).

    ``ALL``: **default.** Same-role pairs are scored too. On a Doppelbesetzung two leaders
    share a position and their working relationship matters, and the team fills the survey in
    expecting those answers to count. Same-role preferences are only ever
    scored when both dancers end up on the same position, which is exactly what the
    ``together`` variables express, so no extra handling is needed.
    """

    ALL = "all"
    CROSS_ROLE_ONLY = "cross_role_only"


class ScoreAggregation(StrEnum):
    """How one dancer's fulfilled wishes combine into their score.

    ``BEST``: the positive part is the weight of the single best fulfilled wish — satisfaction
    saturates once the strongest wish is granted, a second fulfilled wish adds nothing.
    Violated not-desired entries still subtract as a sum. This is the default because it
    matches how the team reads the result: a dancer with their tier-1 partner and no violated
    veto is fully happy, regardless of how many alternatives they listed.

    ``SUM``: the positive part is the sum over all fulfilled wishes, the original semantics.
    """

    BEST = "best"
    SUM = "sum"


class Objective(StrEnum):
    """Objective staging strategy. See ``solver.solve``."""

    LEXIMIN = "leximin"
    WEIGHTED_SUM = "weighted_sum"
    MAXIMIN_THEN_SUM = "maximin_then_sum"
    LEXICOGRAPHIC_TIERS = "lexicographic_tiers"


def position_labels(n_positions: int) -> list[str]:
    """Return the position labels ``["A", "B", ...]`` for ``n_positions`` positions.

    Positions are unordered and interchangeable in the model. They are labelled A-H rather
    than 1-8 so nobody reads a ranking into the result that does not exist.
    """
    if n_positions <= 0:
        raise ValueError("n_positions must be positive")
    labels: list[str] = []
    for index in range(n_positions):
        label = ""
        remainder = index
        while True:
            label = chr(ord("A") + remainder % 26) + label
            remainder = remainder // 26 - 1
            if remainder < 0:
                break
        labels.append(label)
    return labels


def position_label(index: int, n_positions: int = DEFAULT_N_POSITIONS) -> str:
    """Return the label of a single position index."""
    return position_labels(n_positions)[index]


class Dancer(BaseModel):
    """One dancer of the team.

    Attributes:
        id: Stable slug, e.g. ``"lukas-b"``.
        name: Display name.
        role: Leader or follower. Fixed, not a preference.
        is_pole_position: The dancer is the sole driver of their position and must not share
            it with another dancer of the same role. Hard constraint. Formerly
            *Startanspruch* -- note that this is a claim on the starting slot, not a ranking.
        needs_coaching: The dancer must not be the only one of their role on a position, and
            the same-role dancer alongside them must not need coaching themselves — every
            coaching dancer is paired with an experienced dancer of their role. Hard
            constraints. Formerly *Coachingbedarf*.
    """

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    role: Role
    is_pole_position: bool = False
    needs_coaching: bool = False

    @model_validator(mode="after")
    def _flags_are_mutually_exclusive(self) -> Dancer:
        """Validator 1: a pole position and a coaching need contradict each other."""
        if self.is_pole_position and self.needs_coaching:
            raise ValueError(
                f"dancer {self.id!r}: is_pole_position and needs_coaching are mutually exclusive"
            )
        return self


class Tier(BaseModel):
    """One rank of a desired / not-desired partner list.

    Attributes:
        rank: 1 is the strongest preference.
        dancer_ids: Equivalent options within the tier; no ordering inside a tier.
    """

    model_config = ConfigDict(frozen=True)

    rank: int = Field(ge=1)
    dancer_ids: frozenset[str]

    @field_validator("dancer_ids")
    @classmethod
    def _tier_is_not_empty(cls, value: frozenset[str]) -> frozenset[str]:
        if not value:
            raise ValueError("tier must name at least one dancer")
        return value


class Survey(BaseModel):
    """One dancer's complete set of *Teambefragung* answers.

    Preferences are directed: A wishing for B does not imply B wishing for A. Both
    directions are scored independently and are never silently symmetrised.
    """

    model_config = ConfigDict(frozen=True)

    dancer_id: str = Field(min_length=1)
    desired_tiers: list[Tier] = Field(default_factory=list)
    not_desired_tiers: list[Tier] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_tiers(self) -> Survey:
        """Validators 2, 3, 4 and 5."""
        for direction, tiers in (
            ("desired", self.desired_tiers),
            ("not_desired", self.not_desired_tiers),
        ):
            ranks = sorted(tier.rank for tier in tiers)
            if ranks != list(range(1, len(tiers) + 1)):
                raise ValueError(
                    f"survey {self.dancer_id!r}: {direction} tier ranks must be contiguous "
                    f"starting at 1 without duplicates, got {ranks}"
                )
            seen: set[str] = set()
            for tier in tiers:
                overlap = seen & tier.dancer_ids
                if overlap:
                    raise ValueError(
                        f"survey {self.dancer_id!r}: {sorted(overlap)} appear in more than one "
                        f"{direction} tier"
                    )
                seen |= tier.dancer_ids

        wished = self.named_ids("desired")
        unwished = self.named_ids("not_desired")
        both = wished & unwished
        if both:
            raise ValueError(
                f"survey {self.dancer_id!r}: {sorted(both)} appear as both desired and "
                f"not_desired; that is a survey entry error, not a subtle preference"
            )
        if self.dancer_id in wished | unwished:
            raise ValueError(f"survey {self.dancer_id!r}: self-reference is not allowed")
        return self

    def named_ids(self, direction: Direction) -> frozenset[str]:
        """All dancer ids named in one direction, across every tier."""
        tiers = self.desired_tiers if direction == "desired" else self.not_desired_tiers
        return frozenset().union(*(tier.dancer_ids for tier in tiers)) if tiers else frozenset()

    def rank_of(self, dancer_id: str, direction: Direction) -> int | None:
        """The tier rank ``dancer_id`` was named at, or ``None`` if unnamed (neutral)."""
        tiers = self.desired_tiers if direction == "desired" else self.not_desired_tiers
        for tier in tiers:
            if dancer_id in tier.dancer_ids:
                return tier.rank
        return None

    @property
    def max_rank(self) -> int:
        """The largest rank used in either direction, 0 for an empty survey."""
        ranks = [tier.rank for tier in (*self.desired_tiers, *self.not_desired_tiers)]
        return max(ranks, default=0)


class PreferenceEntry(BaseModel):
    """One directed, in-scope survey entry: ``source`` named ``target`` at ``rank``."""

    model_config = ConfigDict(frozen=True)

    source: str
    target: str
    direction: Direction
    rank: int


class Team(BaseModel):
    """The full instance: roster, surveys, and the number of positions to fill."""

    model_config = ConfigDict(frozen=True)

    dancers: list[Dancer]
    surveys: list[Survey] = Field(default_factory=list)
    n_positions: int = Field(default=DEFAULT_N_POSITIONS, ge=1)

    @model_validator(mode="after")
    def _check_references(self) -> Team:
        """Validators 6 and 7."""
        ids = [dancer.id for dancer in self.dancers]
        duplicates = {i for i in ids if ids.count(i) > 1}
        if duplicates:
            raise ValueError(f"duplicate dancer ids: {sorted(duplicates)}")
        known = set(ids)

        surveyed = [survey.dancer_id for survey in self.surveys]
        repeated = {i for i in surveyed if surveyed.count(i) > 1}
        if repeated:
            raise ValueError(f"more than one survey for dancer ids: {sorted(repeated)}")

        for survey in self.surveys:
            if survey.dancer_id not in known:
                raise ValueError(f"survey references unknown dancer id {survey.dancer_id!r}")
            unknown = (survey.named_ids("desired") | survey.named_ids("not_desired")) - known
            if unknown:
                raise ValueError(
                    f"survey {survey.dancer_id!r} references unknown dancer ids {sorted(unknown)}"
                )
        return self

    # -- derived views -------------------------------------------------------------

    @property
    def dancers_by_id(self) -> dict[str, Dancer]:
        """Roster indexed by id."""
        return {dancer.id: dancer for dancer in self.dancers}

    @property
    def surveys_by_id(self) -> dict[str, Survey]:
        """Surveys indexed by the answering dancer's id."""
        return {survey.dancer_id: survey for survey in self.surveys}

    @property
    def positions(self) -> range:
        """The position indices."""
        return range(self.n_positions)

    @property
    def labels(self) -> list[str]:
        """Position labels A-H."""
        return position_labels(self.n_positions)

    def by_role(self, role: Role) -> list[Dancer]:
        """Dancers of one role, in input order (input order defines symmetry breaking)."""
        return [dancer for dancer in self.dancers if dancer.role is role]

    @property
    def max_rank(self) -> int:
        """Largest tier rank appearing anywhere in the instance, 0 if there are no tiers."""
        return max((survey.max_rank for survey in self.surveys), default=0)

    def in_scope(self, source_id: str, target_id: str, scope: PreferenceScope) -> bool:
        """Whether a directed pair may be scored under ``scope``."""
        if source_id == target_id:
            return False
        by_id = self.dancers_by_id
        if scope is PreferenceScope.ALL:
            return True
        return by_id[source_id].role is not by_id[target_id].role

    def preference_entries(self, scope: PreferenceScope) -> Iterator[PreferenceEntry]:
        """Yield every directed, in-scope survey entry.

        Single source of truth for which ordered pairs matter, so ``scoring`` and ``solver``
        cannot disagree about it. Out-of-scope entries are dropped silently: under
        ``CROSS_ROLE_ONLY`` a same-role wish is data the model does not use, not an error.
        """
        directions: tuple[Direction, ...] = ("desired", "not_desired")
        for survey in self.surveys:
            for direction in directions:
                tiers = survey.desired_tiers if direction == "desired" else survey.not_desired_tiers
                for tier in tiers:
                    for target in sorted(tier.dancer_ids):
                        if self.in_scope(survey.dancer_id, target, scope):
                            yield PreferenceEntry(
                                source=survey.dancer_id,
                                target=target,
                                direction=direction,
                                rank=tier.rank,
                            )

    def n_doubled_positions(self, role: Role) -> int:
        """How many positions must carry two dancers of ``role``.

        With ``n`` dancers of a role over ``P`` positions, each holding one or two of them,
        exactly ``n - P`` positions are doubled and ``2P - n`` are single. Doubling is
        counted per role: leader- and follower-doubling are independent here, coupling them
        is a soft preference (``SolverConfig.prefer_coupled``), not a hard constraint.
        """
        return len(self.by_role(role)) - self.n_positions

    def n_single_positions(self, role: Role) -> int:
        """How many positions must carry exactly one dancer of ``role``."""
        return 2 * self.n_positions - len(self.by_role(role))


class SolverConfig(BaseModel):
    """Everything that changes what the solver optimises, but not the instance itself."""

    model_config = ConfigDict(frozen=True)

    objective: Objective = Objective.LEXIMIN
    aggregation: ScoreAggregation = ScoreAggregation.BEST
    """See :class:`ScoreAggregation`. Under ``BEST`` the positive part of a score is never
    halved by ``normalize_double``: halving corrects double-*collection* of summed
    contributions, and a maximum cannot double-collect. Violations keep the halving."""
    scope: PreferenceScope = PreferenceScope.ALL

    veto_tier: int | None = 1
    """Nicht-Wunsch entries at this rank or stronger become hard constraints. ``None``
    disables hard vetoes entirely and leaves dislikes purely to the objective."""

    normalize_double: bool = True
    """Halve the cross-role score of a dancer whose position holds two dancers of the
    opposite role, so the solver does not systematically park well-liked dancers on a
    Doppelbesetzung just to collect two contributions instead of one."""

    prefer_coupled: bool = True
    """Prefer positions where both roles are doubled or neither is (two full couples
    sharing a position). Soft: it is the weakest stage of the objective and can never
    cost a fulfilled wish."""

    tier_slack: int = Field(default=0, ge=0)
    """Slack epsilon for LEXICOGRAPHIC_TIERS: stage *k* may give up this many fulfilled
    tier-*k* wishes if a later tier gains by it. 0 is strict lexicographic order."""

    max_solutions: int = Field(default=50, ge=1)
    """Cap on the enumerated shortlist. 1 skips enumeration entirely."""

    near_optimal_ratio: float = Field(default=0.97, gt=0.0, le=1.0)
    """Which solutions the enumeration accepts. 1.0 means only the exact optima; 0.95 also
    accepts a stage value within 5 % of its optimum. The slack is computed from the absolute
    value of the optimum, so it widens the bound for negative optima too instead of
    tightening it."""

    max_time_in_seconds: float = Field(default=30.0, gt=0)
    random_seed: int = 0
    num_workers: int = Field(default=1, ge=1)
    """1 keeps CP-SAT reproducible, which the determinism requirement depends on."""

    log_search_progress: bool = False

    @model_validator(mode="after")
    def _check_veto_tier(self) -> SolverConfig:
        if self.veto_tier is not None and self.veto_tier < 1:
            raise ValueError("veto_tier must be >= 1 or None")
        return self

    def vetoed_ranks(self, rank: int) -> bool:
        """Whether a not_desired entry at ``rank`` is a hard veto."""
        return self.veto_tier is not None and rank <= self.veto_tier

    @property
    def score_scale(self) -> int:
        """Integer factor every score is multiplied by, so halving needs no rounding."""
        return 2 if self.normalize_double else 1
