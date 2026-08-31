"""YAML persistence: round-tripping, key order, and the shape errors the coach will hit."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from dancepartner.model import Dancer, Role, Survey, Team, Tier
from dancepartner.storage import (
    StorageError,
    dump_team,
    load_team,
    parse_team,
    save_team,
)

from .builders import roster, tier, wunsch

EXAMPLE = Path(__file__).resolve().parents[1] / "data" / "team.example.yaml"

MINIMAL = """
n_positions: 1
dancers:
  - id: h0
    name: H0
    role: herr
  - id: d0
    name: D0
    role: dame
"""


def test_loads_the_shipped_example() -> None:
    team = load_team(EXAMPLE)
    assert len(team.dancers) == 20
    assert len(team.by_role(Role.HERR)) == 9
    assert len(team.by_role(Role.DAME)) == 11
    assert team.n_positions == 8
    assert len(team.surveys) == 19


def test_example_has_mixed_flags_and_tiers() -> None:
    team = load_team(EXAMPLE)
    assert [d.id for d in team.dancers if d.has_startanspruch] == ["tim-r", "sofia-r"]
    assert [d.id for d in team.dancers if d.needs_coaching] == ["paul-m", "leah-d"]
    assert team.max_rank == 2
    lukas = team.surveys_by_id["lukas-b"]
    assert lukas.rank_of("anna-b", "wunsch") == 1
    assert lukas.rank_of("mia-t", "wunsch") == 2
    assert lukas.rank_of("emma-k", "nicht_wunsch") == 1


def test_dancer_order_is_preserved() -> None:
    # Semantically significant: symmetry breaking numbers positions by Herren input order.
    team = load_team(EXAMPLE)
    assert [d.id for d in team.by_role(Role.HERR)][:3] == ["lukas-b", "jonas-k", "tim-r"]
    assert [d.id for d in parse_team(dump_team(team)).dancers] == [d.id for d in team.dancers]


def test_round_trip_is_lossless() -> None:
    team = load_team(EXAMPLE)
    assert parse_team(dump_team(team)) == team


def test_dump_is_idempotent() -> None:
    team = load_team(EXAMPLE)
    once = dump_team(team)
    assert dump_team(parse_team(once)) == once


def test_keys_are_never_sorted_alphabetically() -> None:
    team = Team(
        dancers=[Dancer(id="h0", name="H0", role=Role.HERR, has_startanspruch=True)]
        + [Dancer(id="d0", name="D0", role=Role.DAME)],
        n_positions=1,
    )
    lines = [line.strip() for line in dump_team(team).splitlines()]
    # Alphabetical order would put has_startanspruch first and id after name.
    assert lines[:6] == [
        "n_positions: 1",
        "dancers:",
        "- id: h0",
        "name: H0",
        "role: herr",
        "has_startanspruch: true",
    ]


def test_false_flags_are_omitted() -> None:
    team = Team(dancers=roster(1, 1), n_positions=1)
    text = dump_team(team)
    assert "has_startanspruch" not in text
    assert "needs_coaching" not in text


def test_empty_survey_directions_are_omitted() -> None:
    team = Team(dancers=roster(1, 1), surveys=[wunsch("h0", tier(1, "d0"))], n_positions=1)
    text = dump_team(team)
    assert "wunsch:" in text
    assert "nicht_wunsch" not in text


def test_surveys_key_is_omitted_when_there_are_none() -> None:
    assert "surveys" not in dump_team(Team(dancers=roster(1, 1), n_positions=1))


def test_tier_ids_are_emitted_inline_and_sorted() -> None:
    team = Team(
        dancers=roster(1, 3),
        surveys=[wunsch("h0", tier(1, "d2", "d0", "d1"))],
        n_positions=1,
    )
    assert "1: [d0, d1, d2]" in dump_team(team)


def test_tiers_are_ordered_by_rank_regardless_of_file_order() -> None:
    text = """
n_positions: 1
dancers:
  - {id: h0, name: H0, role: herr}
  - {id: d0, name: D0, role: dame}
  - {id: d1, name: D1, role: dame}
surveys:
  - dancer_id: h0
    wunsch:
      2: [d1]
      1: [d0]
"""
    team = parse_team(text)
    assert [t.rank for t in team.surveys[0].wunsch_tiers] == [1, 2]


def test_save_and_load_round_trip(tmp_path: Path) -> None:
    team = load_team(EXAMPLE)
    target = tmp_path / "nested" / "team.yaml"
    save_team(team, target)
    assert target.exists()
    assert load_team(target) == team


def test_save_accepts_a_string_path(tmp_path: Path) -> None:
    team = parse_team(MINIMAL)
    save_team(team, str(tmp_path / "team.yaml"))
    assert load_team(str(tmp_path / "team.yaml")) == team


def test_umlauts_are_not_escaped() -> None:
    team = Team(
        dancers=[Dancer(id="h0", name="Jörg Hübner", role=Role.HERR), *roster(0, 1)],
        n_positions=1,
    )
    text = dump_team(team)
    assert "Jörg Hübner" in text
    assert "\\u" not in text


# -- error handling -----------------------------------------------------------------------


def test_missing_file_raises_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_team(tmp_path / "nope.yaml")


def test_broken_yaml_raises_storage_error() -> None:
    with pytest.raises(StorageError, match="not valid YAML"):
        parse_team("dancers: [\n  - unclosed")


def test_empty_file_raises_storage_error() -> None:
    with pytest.raises(StorageError, match="empty"):
        parse_team("")


def test_top_level_must_be_a_mapping() -> None:
    with pytest.raises(StorageError, match="expected a mapping"):
        parse_team("- just\n- a list\n")


@pytest.mark.parametrize(
    ("text", "message"),
    [
        pytest.param("dancers: {}\n", "'dancers' must be a list", id="dancers-not-a-list"),
        pytest.param(
            "dancers: []\nsurveys: 3\n", "'surveys' must be a list", id="surveys-not-a-list"
        ),
        pytest.param(
            "dancers: [3]\n", r"dancers\[0\] must be a mapping", id="dancer-not-a-mapping"
        ),
        pytest.param(
            "dancers: [{id: h0, name: H0, role: kapitaen}]\n",
            "role must be one of",
            id="unknown-role",
        ),
        pytest.param(
            "dancers: [{id: h0, name: H0, role: herr, hight: 180}]\n",
            r"unknown key\(s\) \['hight'\]",
            id="typo-in-dancer-key",
        ),
        pytest.param(
            "dancers: []\nn_positions: acht\n", "n_positions must be an integer", id="bad-n"
        ),
        pytest.param(
            "dancers: []\nsurveys: [{dancer_id: h0, wünsche: {}}]\n",
            r"unknown key\(s\)",
            id="typo-in-survey-key",
        ),
        pytest.param(
            "dancers: []\nsurveys: [{dancer_id: h0, wunsch: [d0]}]\n",
            r"surveys\[0\].wunsch must be a mapping",
            id="tiers-not-a-mapping",
        ),
        pytest.param(
            "dancers: []\nsurveys: [{dancer_id: h0, wunsch: {eins: [d0]}}]\n",
            "tier rank must be an integer",
            id="non-integer-rank",
        ),
        pytest.param(
            "dancers: []\nsurveys: [{dancer_id: h0, wunsch: {1: d0}}]\n",
            "expected a list of dancer ids",
            id="tier-not-a-list",
        ),
    ],
)
def test_shape_errors_are_reported_precisely(text: str, message: str) -> None:
    with pytest.raises(StorageError, match=message):
        parse_team(text)


def test_domain_rules_still_raise_validation_error() -> None:
    # Not a StorageError: the shape is fine, the content breaks SPEC.md 6.
    text = """
n_positions: 1
dancers:
  - {id: h0, name: H0, role: herr, has_startanspruch: true, needs_coaching: true}
"""
    with pytest.raises(ValidationError, match="mutually exclusive"):
        parse_team(text)


def test_unknown_reference_raises_validation_error() -> None:
    text = """
n_positions: 1
dancers:
  - {id: h0, name: H0, role: herr}
surveys:
  - dancer_id: h0
    wunsch:
      1: [ghost]
"""
    with pytest.raises(ValidationError, match="unknown dancer ids"):
        parse_team(text)


def test_missing_n_positions_defaults_to_eight() -> None:
    team = parse_team("dancers: [{id: h0, name: H0, role: herr}]\n")
    assert team.n_positions == 8


def test_booleans_are_not_accepted_as_integers() -> None:
    with pytest.raises(StorageError, match="n_positions must be an integer"):
        parse_team("dancers: []\nn_positions: true\n")
    with pytest.raises(StorageError, match="tier rank must be an integer"):
        parse_team("dancers: []\nsurveys: [{dancer_id: h0, wunsch: {true: [d0]}}]\n")


def test_tier_model_is_rebuilt_not_shared() -> None:
    team = parse_team(MINIMAL)
    assert team.surveys == []
    assert Tier(rank=1, dancer_ids=frozenset({"d0"})).dancer_ids == frozenset({"d0"})
    assert Survey(dancer_id="h0").wunsch_tiers == []
