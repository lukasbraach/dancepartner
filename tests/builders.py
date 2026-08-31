"""Terse constructors for hand-built test instances."""

from __future__ import annotations

from dancepartner.model import Dancer, Role, Survey, Team, Tier


def herr(id_: str, **flags: bool) -> Dancer:
    return Dancer(id=id_, name=id_.upper(), role=Role.HERR, **flags)


def dame(id_: str, **flags: bool) -> Dancer:
    return Dancer(id=id_, name=id_.upper(), role=Role.DAME, **flags)


def tier(rank: int, *ids: str) -> Tier:
    return Tier(rank=rank, dancer_ids=frozenset(ids))


def wunsch(dancer_id: str, *tiers: Tier) -> Survey:
    return Survey(dancer_id=dancer_id, wunsch_tiers=list(tiers))


def nicht_wunsch(dancer_id: str, *tiers: Tier) -> Survey:
    return Survey(dancer_id=dancer_id, nicht_wunsch_tiers=list(tiers))


def roster(n_herren: int, n_damen: int, **flags: dict[str, bool]) -> list[Dancer]:
    """``n_herren`` Herren ``h0..`` and ``n_damen`` Damen ``d0..``, flags keyed by dancer id."""
    dancers = [herr(f"h{i}", **flags.get(f"h{i}", {})) for i in range(n_herren)]
    dancers += [dame(f"d{i}", **flags.get(f"d{i}", {})) for i in range(n_damen)]
    return dancers


def team(
    n_herren: int,
    n_damen: int,
    n_positions: int,
    *surveys: Survey,
    **flags: dict[str, bool],
) -> Team:
    """A team with a generated roster and the given surveys."""
    return Team(
        dancers=roster(n_herren, n_damen, **flags),
        surveys=list(surveys),
        n_positions=n_positions,
    )
