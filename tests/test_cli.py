"""CLI behaviour: German output, exit codes, and the JSON contract between solve and explain."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from dancepartner.cli import app
from dancepartner.i18n import STRINGS
from dancepartner.model import Team
from dancepartner.storage import dump_team, load_team

from .builders import roster

EXAMPLE = str(Path(__file__).resolve().parents[1] / "data" / "team.example.yaml")

runner = CliRunner()


def run(*args: str) -> Result:
    return runner.invoke(app, list(args))


# -- check --------------------------------------------------------------------------------


def test_check_reports_a_solvable_team() -> None:
    result = run("check", EXAMPLE)
    assert result.exit_code == 0
    assert "20 Tänzer:innen (9 Herren, 11 Damen)" in result.stdout
    assert "19 von 20" in result.stdout
    assert "Keine zählbaren Hindernisse" in result.stdout


def test_check_reports_issues_and_exits_one(tmp_path: Path) -> None:
    # 3 Herren for 8 positions: decidable by counting.
    path = tmp_path / "team.yaml"
    path.write_text(dump_team(Team(dancers=roster(3, 8), n_positions=8)), encoding="utf-8")
    result = run("check", str(path))
    assert result.exit_code == 1
    assert "ROLE_COUNT_OUT_OF_RANGE" in result.stdout
    assert "Positionen" in result.stdout
    assert "betroffen: h0, h1, h2" in result.stdout


def test_check_missing_file_exits_one(tmp_path: Path) -> None:
    result = run("check", str(tmp_path / "nope.yaml"))
    assert result.exit_code == 1
    assert "Datei nicht gefunden" in result.stderr


def test_check_broken_yaml_exits_one(tmp_path: Path) -> None:
    path = tmp_path / "team.yaml"
    path.write_text("dancers: [\n  - unclosed", encoding="utf-8")
    result = run("check", str(path))
    assert result.exit_code == 1
    assert "kein gültiges YAML" in result.stderr


def test_check_invalid_team_exits_one(tmp_path: Path) -> None:
    path = tmp_path / "team.yaml"
    path.write_text(
        "n_positions: 1\ndancers:\n"
        "  - {id: h0, name: H0, role: herr, has_startanspruch: true, needs_coaching: true}\n",
        encoding="utf-8",
    )
    result = run("check", str(path))
    assert result.exit_code == 1
    assert "ungültig" in result.stderr
    assert "mutually exclusive" in result.stderr


# -- solve --------------------------------------------------------------------------------


def test_solve_prints_positions_and_the_satisfaction_table() -> None:
    result = run("solve", EXAMPLE)
    assert result.exit_code == 0
    assert "Status: OPTIMAL" in result.stdout
    assert "Zielfunktion in Stufen:" in result.stdout
    assert "maximin: 0 (maximiert)" in result.stdout
    assert "coupled: 4 (minimiert)" in result.stdout
    assert "Gesamtpunkte: 55" in result.stdout
    for label in "ABCDEFGH":
        assert f"Position {label}" in result.stdout
    assert "Zufriedenheit (unzufriedenste zuerst):" in result.stdout
    # Positions are labelled, never numbered.
    assert "Position 1" not in result.stdout


def test_solve_table_is_sorted_unhappiest_first() -> None:
    result = run("solve", EXAMPLE)
    body = result.stdout.split("Zufriedenheit (unzufriedenste zuerst):")[1]
    scores = [int(m.group(1)) for m in re.finditer(r"^\S.{19}\s*(-?\d+)\s\s", body, re.M)]
    assert len(scores) == 20
    assert scores == sorted(scores)


def test_solve_respects_objective_and_weight_options() -> None:
    result = run("solve", EXAMPLE, "--objective", "weighted-sum", "--weights", "geometric")
    assert result.exit_code == 0
    assert "maximin" not in result.stdout
    assert "sum:" in result.stdout


def test_solve_no_prefer_coupled_drops_the_stage() -> None:
    result = run("solve", EXAMPLE, "--no-prefer-coupled")
    assert result.exit_code == 0
    assert "coupled" not in result.stdout


def test_solve_veto_tier_zero_means_no_hard_vetoes(tmp_path: Path) -> None:
    # A team that is only infeasible because of vetoes becomes solvable with --veto-tier 0.
    path = tmp_path / "team.yaml"
    path.write_text(
        "n_positions: 1\n"
        "dancers:\n"
        "  - {id: h0, name: H0, role: herr}\n"
        "  - {id: d0, name: D0, role: dame}\n"
        "surveys:\n"
        "  - dancer_id: h0\n    nicht_wunsch:\n      1: [d0]\n",
        encoding="utf-8",
    )
    assert run("solve", str(path)).exit_code == 1
    ok = run("solve", str(path), "--veto-tier", "0")
    assert ok.exit_code == 0


def test_solve_reports_precheck_failure_in_german(tmp_path: Path) -> None:
    path = tmp_path / "team.yaml"
    path.write_text(dump_team(Team(dancers=roster(3, 8), n_positions=8)), encoding="utf-8")
    result = run("solve", str(path))
    assert result.exit_code == 1
    assert "nicht lösbar" in result.stdout
    assert "ROLE_COUNT_OUT_OF_RANGE" in result.stdout


def test_solve_rejects_an_unimplemented_objective() -> None:
    result = run("solve", EXAMPLE, "--objective", "leximin")
    assert result.exit_code == 1
    assert "Milestone 3" in result.stderr


def test_solve_warns_that_top_is_not_wired_yet() -> None:
    result = run("solve", EXAMPLE, "--top", "10")
    assert result.exit_code == 0
    assert "Milestone 3" in result.stdout


def test_solve_top_one_prints_no_warning() -> None:
    assert "--top" not in run("solve", EXAMPLE).stdout


def test_solve_writes_json(tmp_path: Path) -> None:
    out = tmp_path / "nested" / "out.json"
    result = run("solve", EXAMPLE, "--json", str(out))
    assert result.exit_code == 0
    assert f"Ergebnis geschrieben nach {out}" in result.stdout
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["config"]["objective"] == "maximin_then_sum"
    assert payload["result"]["status"] == "OPTIMAL"
    assert len(payload["result"]["solutions"][0]["positions"]) == 8
    # Names must survive as UTF-8, not as \u escapes.
    assert "\\u" not in out.read_text(encoding="utf-8")


def test_solve_is_deterministic_across_runs() -> None:
    first = run("solve", EXAMPLE, "--seed", "11")
    second = run("solve", EXAMPLE, "--seed", "11")
    body = "Positionen:"
    assert first.stdout.split(body)[1] == second.stdout.split(body)[1]


def test_solve_verbose_logs_stages() -> None:
    result = run("solve", EXAMPLE, "--verbose")
    assert result.exit_code == 0


# -- explain ------------------------------------------------------------------------------


@pytest.fixture
def solved(tmp_path: Path) -> Path:
    out = tmp_path / "out.json"
    assert run("solve", EXAMPLE, "--json", str(out)).exit_code == 0
    return out


def test_explain_a_single_dancer(solved: Path) -> None:
    result = run("explain", EXAMPLE, str(solved), "--dancer", "lukas-b")
    assert result.exit_code == 0
    assert "Lukas Brandt (Herr) — Position A" in result.stdout
    assert "Erfüllte Wünsche:" in result.stdout
    assert "Tier 1: Anna Brenner" in result.stdout
    assert "Nicht erfüllte Wünsche:" in result.stdout
    assert "Eingehaltene Nicht-Wünsche:" in result.stdout


def test_explain_reports_coachingbedarf(solved: Path) -> None:
    result = run("explain", EXAMPLE, str(solved), "--dancer", "paul-m")
    assert result.exit_code == 0
    assert "Coachingbedarf: mit Jan Hübner" in result.stdout


def test_explain_reports_startanspruch(solved: Path) -> None:
    result = run("explain", EXAMPLE, str(solved), "--dancer", "tim-r")
    assert result.exit_code == 0
    assert "Startanspruch: alleine" in result.stdout


def test_explain_a_dancer_without_a_survey(solved: Path) -> None:
    result = run("explain", EXAMPLE, str(solved), "--dancer", "marie-g")
    assert result.exit_code == 0
    assert "Keine Teambefragung abgegeben" in result.stdout
    assert "Punkte: 0" in result.stdout


def test_explain_without_a_dancer_prints_the_whole_solution(solved: Path) -> None:
    result = run("explain", EXAMPLE, str(solved))
    assert result.exit_code == 0
    assert "Positionen:" in result.stdout
    assert "Zufriedenheit" in result.stdout


def test_explain_unknown_dancer_exits_one(solved: Path) -> None:
    result = run("explain", EXAMPLE, str(solved), "--dancer", "nobody")
    assert result.exit_code == 1
    assert "Unbekannte Tänzer:in-ID: nobody" in result.stderr


def test_explain_missing_result_file_exits_one(tmp_path: Path) -> None:
    result = run("explain", EXAMPLE, str(tmp_path / "nope.json"))
    assert result.exit_code == 1
    assert "Datei nicht gefunden" in result.stderr


def test_explain_broken_json_exits_one(tmp_path: Path) -> None:
    path = tmp_path / "out.json"
    path.write_text("{not json", encoding="utf-8")
    result = run("explain", EXAMPLE, str(path))
    assert result.exit_code == 1
    assert "kein gültiges YAML" in result.stderr


def test_explain_json_of_the_wrong_shape_exits_one(tmp_path: Path) -> None:
    path = tmp_path / "out.json"
    path.write_text('{"result": {}}', encoding="utf-8")
    result = run("explain", EXAMPLE, str(path))
    assert result.exit_code == 1
    assert "ungültig" in result.stderr


def test_explain_json_without_a_solution_exits_one(tmp_path: Path) -> None:
    path = tmp_path / "out.json"
    path.write_text(
        json.dumps({"config": {}, "result": {"status": "INFEASIBLE", "solutions": []}}),
        encoding="utf-8",
    )
    result = run("explain", EXAMPLE, str(path))
    assert result.exit_code == 1
    assert "ungültig" in result.stderr


def test_explain_matches_the_solve_table(solved: Path) -> None:
    solve_out = run("solve", EXAMPLE).stdout.split("Positionen:")[1]
    explain_out = run("explain", EXAMPLE, str(solved)).stdout.split("Positionen:")[1]
    assert solve_out == explain_out


# -- i18n ---------------------------------------------------------------------------------


def test_help_is_german() -> None:
    result = run("--help")
    assert "Verpartnerung einer Lateinformation" in result.stdout
    assert "Prüft eine Teamdatei" in result.stdout


def test_no_string_key_is_missing_from_i18n() -> None:
    # Every de() call resolves; a missing key raises KeyError and would fail above. This
    # guards the reverse: keys defined but never referenced anywhere in src/.
    source = "\n".join(
        p.read_text(encoding="utf-8")
        for p in (Path(__file__).resolve().parents[1] / "src" / "dancepartner").glob("*.py")
    )
    dynamic_prefixes = ("feasibility.", "role.", "solve.sense.")
    unused = [
        key for key in STRINGS if f'"{key}"' not in source and not key.startswith(dynamic_prefixes)
    ]
    assert unused == []


def test_every_dancer_appears_exactly_once_in_the_solve_output() -> None:
    team = load_team(EXAMPLE)
    stdout = run("solve", EXAMPLE).stdout
    positions = stdout.split("Positionen:")[1].split("Zufriedenheit")[0]
    for dancer in team.dancers:
        assert positions.count(dancer.name) == 1, dancer.name


# -- the boundary between counting and the solver -----------------------------------------

# 2 positions, 2 Herren, 4 Damen: both Damen positions must be doubled. h0 vetoes three of
# the four Damen, so its position cannot be filled with two -- but no pure counting argument
# sees that, which is exactly what feasibility.py documents about itself.
COUNTING_CLEAN_BUT_INFEASIBLE = """
n_positions: 2
dancers:
  - {id: h0, name: H0, role: herr}
  - {id: h1, name: H1, role: herr}
  - {id: d0, name: D0, role: dame}
  - {id: d1, name: D1, role: dame}
  - {id: d2, name: D2, role: dame}
  - {id: d3, name: D3, role: dame}
surveys:
  - dancer_id: h0
    nicht_wunsch:
      1: [d0, d1, d2]
  - dancer_id: h1
    nicht_wunsch:
      1: [d3]
"""


@pytest.fixture
def counting_clean_but_infeasible(tmp_path: Path) -> Path:
    path = tmp_path / "team.yaml"
    path.write_text(COUNTING_CLEAN_BUT_INFEASIBLE, encoding="utf-8")
    return path


def test_check_passes_where_counting_cannot_decide(counting_clean_but_infeasible: Path) -> None:
    result = run("check", str(counting_clean_but_infeasible))
    assert result.exit_code == 0
    assert "Keine zählbaren Hindernisse" in result.stdout
    assert "Endgültig entscheidet der Solver" in result.stdout


def test_solve_reports_no_solution_with_its_own_exit_code(
    counting_clean_but_infeasible: Path,
) -> None:
    result = run("solve", str(counting_clean_but_infeasible))
    assert result.exit_code == 3
    assert "Status: INFEASIBLE" in result.stdout
    assert "Keine Lösung gefunden (Status INFEASIBLE)" in result.stdout


def test_explain_reports_violated_dislikes(counting_clean_but_infeasible: Path) -> None:
    # The same instance becomes solvable once the dislikes stop being hard vetoes, and then
    # one of them is necessarily violated -- which is the branch worth showing the coach.
    out = counting_clean_but_infeasible.parent / "out.json"
    solved_result = run(
        "solve",
        str(counting_clean_but_infeasible),
        "--veto-tier",
        "0",
        "--json",
        str(out),
    )
    assert solved_result.exit_code == 0
    result = run("explain", str(counting_clean_but_infeasible), str(out), "--dancer", "h0")
    assert result.exit_code == 0
    assert "Verletzte Nicht-Wünsche:" in result.stdout
    assert "Eingehaltene Nicht-Wünsche:" in result.stdout


def test_explain_a_dancer_whose_survey_holds_only_dislikes(solved: Path) -> None:
    result = run("explain", EXAMPLE, str(solved), "--dancer", "felix-w")
    assert result.exit_code == 0
    assert "Keine Wünsche erfüllt." in result.stdout
    assert "Eingehaltene Nicht-Wünsche:" in result.stdout
