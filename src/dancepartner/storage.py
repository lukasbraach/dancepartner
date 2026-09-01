"""YAML persistence for a :class:`~dancepartner.model.Team`.

The coach hand-edits this file, so it is optimised for reading and for `git diff`, not for
round-tripping a Python object:

* Keys are emitted in a fixed, meaningful order -- never alphabetically. ``yaml.safe_dump``
  sorts keys by default, which would shuffle ``id``/``name``/``role`` on every save.
* Dancer order is preserved on load **and** save, because it is semantically significant: the
  solver's symmetry breaking numbers positions by the input index of the leaders.
* Tiers are written as a ``rank -> [dancer ids]`` mapping rather than a list of objects. The
  model stores ``dancer_ids`` as a ``frozenset``, so ids are emitted sorted to keep saves
  deterministic.
* ``is_pole_position`` and ``needs_coaching`` are omitted when false, and empty survey
  directions are omitted entirely.

Known limitation: PyYAML cannot preserve comments, so serialising drops any the coach wrote.
Loading never touches the file, and the CLI only ever writes when asked to, so hand-maintained
comments survive as long as nothing writes over that path. The UI never writes at all -- it
offers ``dump_team`` as a download the coach has to press -- for the same reason.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .model import Dancer, Role, Survey, Team, Tier

__all__ = [
    "MalformedYamlError",
    "StorageError",
    "dump_team",
    "load_team",
    "parse_team",
    "save_team",
]

_DANCER_KEYS = ("id", "name", "role", "is_pole_position", "needs_coaching")


class _FlowList(list[str]):
    """A list emitted inline as ``[a, b]``.

    Used for the dancer ids inside a tier: ``1: [anna-b, lena-f]`` reads like the survey form
    the answers came from, and a tier rarely holds more than three names.
    """


class _TeamDumper(yaml.SafeDumper):
    """SafeDumper that indents sequences under their key, as a human would write them."""

    def increase_indent(self, flow: bool = False, indentless: bool = False) -> None:
        # PyYAML puts "- item" in the same column as its parent key; nobody hand-writes YAML
        # that way, and it makes a nested survey block hard to scan.
        super().increase_indent(flow=flow, indentless=False)


_TeamDumper.add_representer(
    _FlowList,
    lambda dumper, data: dumper.represent_sequence("tag:yaml.org,2002:seq", data, flow_style=True),
)


class StorageError(ValueError):
    """The file is not a readable team definition.

    Distinct from ``pydantic.ValidationError``: this one means the YAML *shape* is wrong -- an
    unknown key, a list where a mapping belongs -- not that the domain rules were broken.
    """


class MalformedYamlError(StorageError):
    """The file is not valid YAML at all.

    Separate from its parent so callers can tell "you have a syntax error" from "your keys are
    wrong". Telling somebody their YAML is invalid when it parses perfectly well sends them
    hunting for a missing colon that is not there.
    """


def load_team(path: Path | str) -> Team:
    """Load a team from a YAML file.

    Raises:
        FileNotFoundError: No file at ``path``.
        MalformedYamlError: The file is not valid YAML.
        StorageError: The file parses but is not shaped like a team.
        pydantic.ValidationError: The team violates a domain rule from SPEC.md 6.
    """
    text = Path(path).read_text(encoding="utf-8")
    return parse_team(text)


def parse_team(text: str) -> Team:
    """Parse a team from a YAML string. See :func:`load_team`."""
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise MalformedYamlError(f"not valid YAML: {error}") from error
    if raw is None:
        raise StorageError("the team file is empty")
    if not isinstance(raw, dict):
        raise StorageError(f"expected a mapping at the top level, found {type(raw).__name__}")

    dancers = [_parse_dancer(entry, index) for index, entry in enumerate(_seq(raw, "dancers"))]
    surveys = [_parse_survey(entry, index) for index, entry in enumerate(_seq(raw, "surveys"))]
    n_positions = raw.get("n_positions", 8)
    if not isinstance(n_positions, int) or isinstance(n_positions, bool):
        raise StorageError(f"n_positions must be an integer, found {n_positions!r}")
    return Team(dancers=dancers, surveys=surveys, n_positions=n_positions)


def save_team(team: Team, path: Path | str) -> None:
    """Write a team to a YAML file, creating parent directories as needed."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(dump_team(team), encoding="utf-8")


def dump_team(team: Team) -> str:
    """Serialise a team to the canonical YAML text that :func:`save_team` writes."""
    payload: dict[str, Any] = {
        "n_positions": team.n_positions,
        "dancers": [_dump_dancer(dancer) for dancer in team.dancers],
    }
    if team.surveys:
        payload["surveys"] = [_dump_survey(survey) for survey in team.surveys]
    text = yaml.dump(
        payload,
        Dumper=_TeamDumper,
        # sort_keys=False is the whole point: the key order above is the documented one.
        sort_keys=False,
        allow_unicode=True,  # names carry umlauts; escaping them ruins the diff
        default_flow_style=False,
        width=100,
        indent=2,
    )
    return str(text)


# -- loading ------------------------------------------------------------------------------


def _seq(raw: dict[str, Any], key: str) -> list[object]:
    value = raw.get(key)
    if value is None:
        return []
    if not isinstance(value, list):
        raise StorageError(f"{key!r} must be a list, found {type(value).__name__}")
    return value


def _mapping(entry: object, where: str) -> dict[str, Any]:
    if not isinstance(entry, dict):
        raise StorageError(f"{where} must be a mapping, found {type(entry).__name__}")
    return entry


def _parse_dancer(entry: object, index: int) -> Dancer:
    mapping = _mapping(entry, f"dancers[{index}]")
    unknown = set(mapping) - set(_DANCER_KEYS)
    if unknown:
        raise StorageError(f"dancers[{index}]: unknown key(s) {sorted(unknown)}")
    role = mapping.get("role")
    if role not in tuple(Role):
        raise StorageError(
            f"dancers[{index}]: role must be one of {[r.value for r in Role]}, found {role!r}"
        )
    return Dancer(
        id=str(mapping.get("id", "")),
        name=str(mapping.get("name", "")),
        role=Role(role),
        is_pole_position=bool(mapping.get("is_pole_position", False)),
        needs_coaching=bool(mapping.get("needs_coaching", False)),
    )


def _parse_survey(entry: object, index: int) -> Survey:
    mapping = _mapping(entry, f"surveys[{index}]")
    unknown = set(mapping) - {"dancer_id", "desired", "not_desired"}
    if unknown:
        raise StorageError(f"surveys[{index}]: unknown key(s) {sorted(unknown)}")
    return Survey(
        dancer_id=str(mapping.get("dancer_id", "")),
        desired_tiers=_parse_tiers(mapping.get("desired"), f"surveys[{index}].desired"),
        not_desired_tiers=_parse_tiers(mapping.get("not_desired"), f"surveys[{index}].not_desired"),
    )


def _parse_tiers(raw: object, where: str) -> list[Tier]:
    """Parse a ``rank -> [dancer ids]`` mapping into tiers, ordered by rank."""
    if raw is None:
        return []
    mapping = _mapping(raw, where)
    tiers: list[Tier] = []
    for rank, ids in mapping.items():
        if not isinstance(rank, int) or isinstance(rank, bool):
            raise StorageError(f"{where}: tier rank must be an integer, found {rank!r}")
        if not isinstance(ids, list):
            raise StorageError(
                f"{where}[{rank}]: expected a list of dancer ids, found {type(ids).__name__}"
            )
        tiers.append(Tier(rank=rank, dancer_ids=frozenset(str(i) for i in ids)))
    return sorted(tiers, key=lambda tier: tier.rank)


# -- dumping ------------------------------------------------------------------------------


def _dump_dancer(dancer: Dancer) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "id": dancer.id,
        "name": dancer.name,
        "role": dancer.role.value,
    }
    # Omitted when false: two extra lines per dancer would bury the flags that are actually set.
    if dancer.is_pole_position:
        entry["is_pole_position"] = True
    if dancer.needs_coaching:
        entry["needs_coaching"] = True
    return entry


def _dump_survey(survey: Survey) -> dict[str, Any]:
    entry: dict[str, Any] = {"dancer_id": survey.dancer_id}
    if survey.desired_tiers:
        entry["desired"] = _dump_tiers(survey.desired_tiers)
    if survey.not_desired_tiers:
        entry["not_desired"] = _dump_tiers(survey.not_desired_tiers)
    return entry


def _dump_tiers(tiers: list[Tier]) -> dict[int, _FlowList]:
    return {
        tier.rank: _FlowList(sorted(tier.dancer_ids))
        for tier in sorted(tiers, key=lambda t: t.rank)
    }
