"""Terse constructors for hand-built test instances."""

from __future__ import annotations

from dancepartner.model import CoachConstraints, Dancer, Role, Survey, Team, Tier


def leader(id_: str, **flags: bool) -> Dancer:
    return Dancer(id=id_, name=id_.upper(), role=Role.LEADER, **flags)


def follower(id_: str, **flags: bool) -> Dancer:
    return Dancer(id=id_, name=id_.upper(), role=Role.FOLLOWER, **flags)


def tier(rank: int, *ids: str) -> Tier:
    return Tier(rank=rank, dancer_ids=frozenset(ids))


def desired(dancer_id: str, *tiers: Tier) -> Survey:
    return Survey(dancer_id=dancer_id, desired_tiers=list(tiers))


def not_desired(dancer_id: str, *tiers: Tier) -> Survey:
    return Survey(dancer_id=dancer_id, not_desired_tiers=list(tiers))


def together(*groups: tuple[str, ...]) -> CoachConstraints:
    """Coach rules of the "must share a position" kind."""
    return CoachConstraints(together=[frozenset(group) for group in groups])


def apart(*groups: tuple[str, ...]) -> CoachConstraints:
    """Coach rules of the "must not share a position" kind."""
    return CoachConstraints(apart=[frozenset(group) for group in groups])


def roster(n_leaders: int, n_followers: int, **flags: dict[str, bool]) -> list[Dancer]:
    """``n_leaders`` leaders ``led0..`` plus ``n_followers`` followers ``fol0..``.

    ``flags`` is keyed by dancer id, e.g. ``roster(4, 4, led0={"is_pole_position": True})``.
    Roster order is significant -- the solver's symmetry breaking numbers positions by the
    input index of the leaders -- so these ids double as the canonical ordering in tests.
    """
    dancers = [leader(f"led{i}", **flags.get(f"led{i}", {})) for i in range(n_leaders)]
    dancers += [follower(f"fol{i}", **flags.get(f"fol{i}", {})) for i in range(n_followers)]
    return dancers


def team(
    n_leaders: int,
    n_followers: int,
    n_positions: int,
    *surveys: Survey,
    **flags: dict[str, bool],
) -> Team:
    """A team with a generated roster and the given surveys."""
    return Team(
        dancers=roster(n_leaders, n_followers, **flags),
        surveys=list(surveys),
        n_positions=n_positions,
    )


def with_coach(instance: Team, constraints: CoachConstraints) -> Team:
    """The same instance with the coach's rules attached.

    A separate step rather than a keyword on ``team``: the flags there arrive as ``**flags``,
    and a keyword beside them cannot be typed without every ``**{"led0": ...}`` call site
    becoming ambiguous to mypy.
    """
    return Team(
        dancers=list(instance.dancers),
        surveys=list(instance.surveys),
        n_positions=instance.n_positions,
        coach_constraints=constraints,
    )
