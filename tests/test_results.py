"""The JSON contract shared by ``solve --json``, ``explain`` and the UI's export (SPEC.md 11)."""

from __future__ import annotations

import json

import pytest

from dancepartner.model import Objective, SolverConfig
from dancepartner.results import dump_result_json, parse_result_json, result_payload
from dancepartner.solver import solve

from .builders import desired, team, tier


def _solved() -> tuple[object, SolverConfig]:
    config = SolverConfig(objective=Objective.WEIGHTED_SUM, max_solutions=1)
    return solve(team(3, 3, 3, desired("led0", tier(1, "fol0"))), config), config


def test_dump_result_json_is_the_cli_contract() -> None:
    result, config = _solved()
    text = dump_result_json(result, config)  # type: ignore[arg-type]
    assert text.endswith("\n")
    assert "\\u" not in text, "UTF-8, not escaped -- names carry umlauts"
    payload = json.loads(text)
    assert set(payload) == {"config", "result"}
    assert payload == result_payload(result, config)  # type: ignore[arg-type]


def test_parse_result_json_round_trips() -> None:
    result, config = _solved()
    parsed, parsed_config = parse_result_json(dump_result_json(result, config))  # type: ignore[arg-type]
    assert parsed == result
    assert parsed_config == config


@pytest.mark.parametrize(
    "text",
    [
        '{"config": {}}',
        '{"result": [], "config": {}}',
        '{"result": {"status": "OPTIMAL", "solutions": []}, "config": {}}',
        '{"result": {"status": "OPTIMAL", "solutions": []}, "config": {"objective": "nonsense"}}',
    ],
)
def test_parse_result_json_rejects_the_wrong_shape_with_one_exception_type(text: str) -> None:
    with pytest.raises(ValueError):
        parse_result_json(text)
