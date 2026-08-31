"""CLI behaviour: localized output, exit codes, and the JSON contract between solve and explain."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from dancepartner.cli import app
from dancepartner.i18n import TABLES, Language, set_language
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
    assert "20 dancers (9 leaders, 11 followers)" in result.stdout
    assert "19 of 20" in result.stdout
    assert "No countable obstacles" in result.stdout


def test_check_reports_issues_and_exits_one(tmp_path: Path) -> None:
    # 3 leaders for 8 positions: decidable by counting.
    path = tmp_path / "team.yaml"
    path.write_text(dump_team(Team(dancers=roster(3, 8), n_positions=8)), encoding="utf-8")
    result = run("check", str(path))
    assert result.exit_code == 1
    assert "ROLE_COUNT_OUT_OF_RANGE" in result.stdout
    assert "positions" in result.stdout
    assert "involved: led0, led1, led2" in result.stdout


def test_check_missing_file_exits_one(tmp_path: Path) -> None:
    result = run("check", str(tmp_path / "nope.yaml"))
    assert result.exit_code == 1
    assert "File not found" in result.stderr


def test_check_broken_yaml_exits_one(tmp_path: Path) -> None:
    path = tmp_path / "team.yaml"
    path.write_text("dancers: [\n  - unclosed", encoding="utf-8")
    result = run("check", str(path))
    assert result.exit_code == 1
    assert "not valid YAML" in result.stderr


def test_check_reports_a_shape_error_without_blaming_the_yaml_syntax(tmp_path: Path) -> None:
    # A file in the pre-M3 German vocabulary is well-formed YAML with the wrong keys; the
    # message has to say so, or the coach goes looking for a syntax error that is not there.
    path = tmp_path / "team.yaml"
    path.write_text(
        "n_positions: 1\ndancers:\n  - {id: a, name: A, role: leader, has_pole_position: true}\n",
        encoding="utf-8",
    )
    result = run("check", str(path))
    assert result.exit_code == 1
    assert "not have the expected structure" in result.stderr
    assert "has_pole_position" in result.stderr
    assert "YAML" not in result.stderr


@pytest.mark.parametrize(
    ("entry", "needle"),
    [
        pytest.param("role: herr", "role must be one of", id="old-role-value"),
        pytest.param(
            "role: leader, has_startanspruch: true", "has_startanspruch", id="old-flag-key"
        ),
    ],
)
def test_check_rejects_the_pre_rename_vocabulary(tmp_path: Path, entry: str, needle: str) -> None:
    """There is no backwards compatibility; the error must name the offending key."""
    path = tmp_path / "team.yaml"
    path.write_text(
        f"n_positions: 1\ndancers:\n  - {{id: a, name: A, {entry}}}\n", encoding="utf-8"
    )
    result = run("check", str(path))
    assert result.exit_code == 1
    assert needle in result.stderr


def test_check_rejects_the_old_survey_keys(tmp_path: Path) -> None:
    path = tmp_path / "team.yaml"
    path.write_text(
        "n_positions: 1\ndancers:\n  - {id: a, name: A, role: leader}\n"
        "surveys:\n  - {dancer_id: a, wunsch: {1: [a]}}\n",
        encoding="utf-8",
    )
    result = run("check", str(path))
    assert result.exit_code == 1
    assert "wunsch" in result.stderr


def test_check_invalid_team_exits_one(tmp_path: Path) -> None:
    path = tmp_path / "team.yaml"
    path.write_text(
        "n_positions: 1\ndancers:\n"
        "  - {id: led0, name: LED0, role: leader, is_pole_position: true, needs_coaching: true}\n",
        encoding="utf-8",
    )
    result = run("check", str(path))
    assert result.exit_code == 1
    assert "invalid" in result.stderr
    assert "mutually exclusive" in result.stderr


# -- solve --------------------------------------------------------------------------------


def test_solve_prints_positions_and_the_satisfaction_table() -> None:
    result = run("solve", EXAMPLE)
    assert result.exit_code == 0
    assert "Status: OPTIMAL" in result.stdout
    assert "Objective in stages:" in result.stdout
    assert "maximin: 0 (maximized)" in result.stdout
    assert "coupled: 2 (minimized)" in result.stdout
    assert "Total score: 60" in result.stdout
    for label in "ABCDEFGH":
        assert f"Position {label}" in result.stdout
    assert "Satisfaction (least satisfied first):" in result.stdout
    # Positions are labelled, never numbered.
    assert "Position 1" not in result.stdout


def test_solve_table_is_sorted_unhappiest_first() -> None:
    result = run("solve", EXAMPLE)
    body = result.stdout.split("Satisfaction (least satisfied first):")[1]
    scores = [int(m.group(1)) for m in re.finditer(r"^\S.{19}\s*(-?\d+)\s\s", body, re.M)]
    assert len(scores) == 20
    assert scores == sorted(scores)


def test_solve_maps_the_aggregation_option_into_the_config(tmp_path: Path) -> None:
    out = tmp_path / "out.json"
    assert run("solve", EXAMPLE, "--aggregation", "sum", "--json", str(out)).exit_code == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["config"]["aggregation"] == "sum"
    default = tmp_path / "default.json"
    assert run("solve", EXAMPLE, "--json", str(default)).exit_code == 0
    assert json.loads(default.read_text(encoding="utf-8"))["config"]["aggregation"] == "best"


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
        "  - {id: led0, name: LED0, role: leader}\n"
        "  - {id: fol0, name: FOL0, role: follower}\n"
        "surveys:\n"
        "  - dancer_id: led0\n    not_desired:\n      1: [fol0]\n",
        encoding="utf-8",
    )
    assert run("solve", str(path)).exit_code == 1
    ok = run("solve", str(path), "--veto-tier", "0")
    assert ok.exit_code == 0


def test_solve_reports_precheck_failure(tmp_path: Path) -> None:
    path = tmp_path / "team.yaml"
    path.write_text(dump_team(Team(dancers=roster(3, 8), n_positions=8)), encoding="utf-8")
    result = run("solve", str(path))
    assert result.exit_code == 1
    assert "not solvable" in result.stdout
    assert "ROLE_COUNT_OUT_OF_RANGE" in result.stdout


@pytest.mark.parametrize(
    "objective", ["weighted-sum", "maximin-then-sum", "leximin", "lexicographic-tiers"]
)
def test_solve_accepts_every_objective_by_its_hyphenated_name(objective: str) -> None:
    result = run("solve", EXAMPLE, "--objective", objective)
    assert result.exit_code == 0
    assert "Status: OPTIMAL" in result.stdout


def test_solve_leximin_prints_its_rounds() -> None:
    result = run("solve", EXAMPLE, "--objective", "leximin")
    assert result.exit_code == 0
    assert "leximin.1.floor" in result.stdout
    assert "leximin.1.count" in result.stdout
    assert "sum:" not in result.stdout


def test_solve_tier_objective_prints_tier_stages() -> None:
    result = run("solve", EXAMPLE, "--objective", "lexicographic-tiers")
    assert result.exit_code == 0
    assert "desired.tier1" in result.stdout
    assert "not_desired.tier1" in result.stdout


# -- the shortlist ------------------------------------------------------------------------


def test_solve_top_one_prints_a_single_solution() -> None:
    stdout = run("solve", EXAMPLE).stdout
    assert "1 equally good" in stdout
    assert "Solution 1 of" not in stdout


def test_solve_top_three_prints_both_optima_with_diffs() -> None:
    result = run("solve", EXAMPLE, "--top", "3")
    assert result.exit_code == 0
    # The example team has exactly two optima, so nothing may be reported as cut off.
    assert "2 equally good solution(s) found." in result.stdout
    assert "cut off" not in result.stdout
    for index in (1, 2):
        assert f"Solution {index} of 2" in result.stdout
    assert "(best)" in result.stdout
    assert result.stdout.count("Difference to solution 1:") == 1


def test_solve_top_three_prints_the_exchange_group() -> None:
    result = run("solve", EXAMPLE, "--top", "3")
    assert result.exit_code == 0
    assert "Exchange groups" in result.stdout
    assert "Group 1: Leah Dorn" in result.stdout
    assert "Leah Dorn → F — in solution(s) 1" in result.stdout
    assert "Leah Dorn → G — in solution(s) 2" in result.stdout


def test_solve_lists_per_dancer_options_for_a_large_group(tmp_path: Path) -> None:
    # No surveys: every assignment is optimal, so the group collects far more constellations
    # than anyone can read -- the block must fall back to one options line per dancer.
    path = tmp_path / "team.yaml"
    path.write_text(dump_team(Team(dancers=roster(10, 12), n_positions=8)), encoding="utf-8")
    result = run("solve", str(path), "--top", "8")
    assert result.exit_code == 0
    assert "constellations — see the individual solutions." in result.stdout
    assert "→" not in result.stdout.split("Exchange groups")[1].split("── Solution")[0]


def test_solve_top_one_prints_no_group_block() -> None:
    result = run("solve", EXAMPLE)
    assert result.exit_code == 0
    assert "Exchange groups" not in result.stdout


def test_solve_reports_a_truncated_shortlist(tmp_path: Path) -> None:
    # No surveys at all: every assignment is optimal, so the cap must bite and say so.
    path = tmp_path / "team.yaml"
    path.write_text(dump_team(Team(dancers=roster(10, 12), n_positions=8)), encoding="utf-8")
    result = run("solve", str(path), "--top", "4")
    assert result.exit_code == 0
    assert "cut off" in result.stdout
    assert result.stdout.count("Difference to solution 1:") == 3


def test_solve_near_optimal_widens_the_shortlist() -> None:
    exact = run("solve", EXAMPLE, "--top", "20")
    loose = run("solve", EXAMPLE, "--top", "20", "--near-optimal", "0.95")
    assert loose.exit_code == 0
    assert "95 % of the optimum" in loose.stdout
    assert loose.stdout.count("Difference to solution 1:") > exact.stdout.count(
        "Difference to solution 1:"
    )


def test_solve_tier_slack_is_reported_when_it_is_spent() -> None:
    result = run("solve", EXAMPLE, "--objective", "lexicographic-tiers", "--tier-slack", "2")
    assert result.exit_code == 0
    assert "locked in: at least" in result.stdout


def test_solve_json_carries_the_whole_shortlist(tmp_path: Path) -> None:
    out = tmp_path / "out.json"
    assert run("solve", EXAMPLE, "--top", "3", "--json", str(out)).exit_code == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert len(payload["result"]["solutions"]) == 2
    assert payload["config"]["max_solutions"] == 3
    assert payload["result"]["truncated"] is False


def test_solve_writes_json(tmp_path: Path) -> None:
    out = tmp_path / "nested" / "out.json"
    result = run("solve", EXAMPLE, "--json", str(out))
    assert result.exit_code == 0
    assert f"Result written to {out}" in result.stdout
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["config"]["objective"] == "maximin_then_sum"
    assert payload["result"]["status"] == "OPTIMAL"
    assert len(payload["result"]["solutions"][0]["positions"]) == 8
    # Names must survive as UTF-8, not as \u escapes.
    assert "\\u" not in out.read_text(encoding="utf-8")


def test_solve_is_deterministic_across_runs() -> None:
    first = run("solve", EXAMPLE, "--seed", "11")
    second = run("solve", EXAMPLE, "--seed", "11")
    body = "Positions:"
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


@pytest.fixture
def shortlisted(tmp_path: Path) -> Path:
    out = tmp_path / "top3.json"
    assert run("solve", EXAMPLE, "--top", "3", "--json", str(out)).exit_code == 0
    return out


def test_explain_a_single_dancer(solved: Path) -> None:
    result = run("explain", EXAMPLE, str(solved), "--dancer", "lukas-b")
    assert result.exit_code == 0
    assert "Lukas Brandt (Leader) — Position A" in result.stdout
    assert "Fulfilled wishes:" in result.stdout
    assert "Tier 1: Anna Brenner" in result.stdout
    assert "Unfulfilled wishes:" in result.stdout
    assert "Respected not-desired wishes:" in result.stdout
    # BEST is the default: a fulfilled top-tier wish is full satisfaction.
    assert "Satisfaction: 100 %" in result.stdout


def test_explain_prints_no_satisfaction_percent_under_sum(tmp_path: Path) -> None:
    out = tmp_path / "sum.json"
    assert run("solve", EXAMPLE, "--aggregation", "sum", "--json", str(out)).exit_code == 0
    result = run("explain", EXAMPLE, str(out), "--dancer", "lukas-b")
    assert result.exit_code == 0
    assert "Satisfaction:" not in result.stdout


def test_explain_reports_coaching_need(solved: Path) -> None:
    result = run("explain", EXAMPLE, str(solved), "--dancer", "paul-m")
    assert result.exit_code == 0
    assert "Coaching need: with Jan Hübner" in result.stdout


def test_explain_reports_pole_position(solved: Path) -> None:
    result = run("explain", EXAMPLE, str(solved), "--dancer", "tim-r")
    assert result.exit_code == 0
    assert "Pole position: alone" in result.stdout


def test_explain_a_dancer_without_a_survey(solved: Path) -> None:
    result = run("explain", EXAMPLE, str(solved), "--dancer", "marie-g")
    assert result.exit_code == 0
    assert "No team survey submitted" in result.stdout
    assert "Score: 0" in result.stdout
    # Neutral is not unhappy: no percentage is claimed for a dancer who stated nothing.
    assert "Satisfaction:" not in result.stdout


def test_explain_without_a_dancer_prints_the_whole_solution(solved: Path) -> None:
    result = run("explain", EXAMPLE, str(solved))
    assert result.exit_code == 0
    assert "Positions:" in result.stdout
    assert "Satisfaction" in result.stdout


def test_explain_unknown_dancer_exits_one(solved: Path) -> None:
    result = run("explain", EXAMPLE, str(solved), "--dancer", "nobody")
    assert result.exit_code == 1
    assert "Unknown dancer ID: nobody" in result.stderr


def test_explain_missing_result_file_exits_one(tmp_path: Path) -> None:
    result = run("explain", EXAMPLE, str(tmp_path / "nope.json"))
    assert result.exit_code == 1
    assert "File not found" in result.stderr


def test_explain_broken_json_exits_one(tmp_path: Path) -> None:
    path = tmp_path / "out.json"
    path.write_text("{not json", encoding="utf-8")
    result = run("explain", EXAMPLE, str(path))
    assert result.exit_code == 1
    assert "not valid JSON" in result.stderr


def test_explain_json_of_the_wrong_shape_exits_one(tmp_path: Path) -> None:
    path = tmp_path / "out.json"
    path.write_text('{"result": {}}', encoding="utf-8")
    result = run("explain", EXAMPLE, str(path))
    assert result.exit_code == 1
    assert "invalid" in result.stderr


def test_explain_picks_a_solution_by_index(shortlisted: Path) -> None:
    first = run("explain", EXAMPLE, str(shortlisted), "--dancer", "david-l", "--solution", "1")
    second = run("explain", EXAMPLE, str(shortlisted), "--dancer", "david-l", "--solution", "2")
    assert first.exit_code == second.exit_code == 0
    assert "(from solution 1 of 2)" in first.stdout
    assert "(from solution 2 of 2)" in second.stdout
    # David Lorenz' second partner is exactly what the two optima disagree about.
    assert first.stdout != second.stdout


def test_explain_rejects_a_solution_index_out_of_range(shortlisted: Path) -> None:
    result = run("explain", EXAMPLE, str(shortlisted), "--solution", "9")
    assert result.exit_code == 1
    assert "only 2 solution(s)" in result.stderr


def test_explain_summarises_a_dancer_across_the_shortlist(shortlisted: Path) -> None:
    result = run("explain", EXAMPLE, str(shortlisted), "--dancer", "david-l")
    assert result.exit_code == 0
    assert "Across all 2 solutions:" in result.stdout
    # Nina is fixed; Leah is the actual open question.
    assert "Nina Steinbach: in 2 of 2 solutions" in result.stdout
    assert "Leah Dorn: in 1 of 2 solutions" in result.stdout


def test_explain_names_the_exchange_group(shortlisted: Path) -> None:
    result = run("explain", EXAMPLE, str(shortlisted), "--dancer", "leah-d")
    assert result.exit_code == 0
    assert "Exchange group 1: Leah Dorn" in result.stdout


def test_explain_says_when_a_dancer_has_no_open_choice(shortlisted: Path) -> None:
    result = run("explain", EXAMPLE, str(shortlisted), "--dancer", "lukas-b")
    assert result.exit_code == 0
    assert "the same in all 2 solutions" in result.stdout
    assert "Exchange group" not in result.stdout


def test_explain_adds_no_cross_solution_note_for_a_single_solution(solved: Path) -> None:
    result = run("explain", EXAMPLE, str(solved), "--dancer", "lukas-b")
    assert result.exit_code == 0
    assert "Across all" not in result.stdout
    assert "from solution" not in result.stdout
    assert "Exchange group" not in result.stdout


def test_explain_json_without_a_solution_exits_one(tmp_path: Path) -> None:
    path = tmp_path / "out.json"
    path.write_text(
        json.dumps({"config": {}, "result": {"status": "INFEASIBLE", "solutions": []}}),
        encoding="utf-8",
    )
    result = run("explain", EXAMPLE, str(path))
    assert result.exit_code == 1
    assert "invalid" in result.stderr


def test_explain_matches_the_solve_table(solved: Path) -> None:
    solve_out = run("solve", EXAMPLE).stdout.split("Positions:")[1]
    explain_out = run("explain", EXAMPLE, str(solved)).stdout.split("Positions:")[1]
    assert solve_out == explain_out


# -- i18n ---------------------------------------------------------------------------------


def test_help_is_english() -> None:
    result = run("--help")
    assert "Partnering a Latin formation team" in result.stdout
    assert "Checks a team file" in result.stdout


@pytest.mark.parametrize("language", list(Language))
def test_check_speaks_the_active_language(language: Language) -> None:
    set_language(language)
    result = run("check", EXAMPLE)
    assert result.exit_code == 0
    assert TABLES[language]["check.ok"] in result.stdout


def test_the_environment_variable_selects_the_language_at_import() -> None:
    # Typer help texts resolve at import time, so only a fresh process shows the effect.
    proc = subprocess.run(
        [sys.executable, "-c", "from dancepartner.cli import app; app(['--help'])"],
        capture_output=True,
        text=True,
        env={**os.environ, "DANCEPARTNER_LANG": "de", "COLUMNS": "200"},
        check=False,
    )
    assert "Verpartnerung einer Lateinformation" in proc.stdout
    assert "Prüft eine Teamdatei" in proc.stdout


def test_no_string_key_is_missing_from_i18n() -> None:
    # Every t() call resolves; a missing key raises KeyError and would fail above. This
    # guards the reverse: keys defined but never referenced. The UI is a second consumer of
    # the tables, so app/ counts as a reference site too -- otherwise every ui. key looks
    # unused. Key-set parity between the tables is covered by test_i18n.py, so scanning the
    # English table covers both.
    root = Path(__file__).resolve().parents[1]
    sources = [*(root / "src" / "dancepartner").glob("*.py"), *(root / "app").rglob("*.py")]
    source = "\n".join(p.read_text(encoding="utf-8") for p in sources)
    dynamic_prefixes = (
        "feasibility.",
        "language.",
        "role.",
        "solve.sense.",
        "ui.objective.",
        "ui.weights.",
        "ui.aggregation.",
        "ui.scope.",
    )
    unused = [
        key
        for key in TABLES[Language.EN]
        if f'"{key}"' not in source and not key.startswith(dynamic_prefixes)
    ]
    assert unused == []


def test_every_dancer_appears_exactly_once_in_the_solve_output() -> None:
    team = load_team(EXAMPLE)
    stdout = run("solve", EXAMPLE).stdout
    positions = stdout.split("Positions:")[1].split("Satisfaction")[0]
    for dancer in team.dancers:
        assert positions.count(dancer.name) == 1, dancer.name


# -- the boundary between counting and the solver -----------------------------------------

# 2 positions, 2 leaders, 4 followers: both follower positions must be doubled. led0 vetoes
# three of the four followers, so its position cannot be filled with two -- but no pure
# counting argument sees that, which is exactly what feasibility.py documents about itself.
COUNTING_CLEAN_BUT_INFEASIBLE = """
n_positions: 2
dancers:
  - {id: led0, name: LED0, role: leader}
  - {id: led1, name: LED1, role: leader}
  - {id: fol0, name: FOL0, role: follower}
  - {id: fol1, name: FOL1, role: follower}
  - {id: fol2, name: FOL2, role: follower}
  - {id: fol3, name: FOL3, role: follower}
surveys:
  - dancer_id: led0
    not_desired:
      1: [fol0, fol1, fol2]
  - dancer_id: led1
    not_desired:
      1: [fol3]
"""


@pytest.fixture
def counting_clean_but_infeasible(tmp_path: Path) -> Path:
    path = tmp_path / "team.yaml"
    path.write_text(COUNTING_CLEAN_BUT_INFEASIBLE, encoding="utf-8")
    return path


def test_check_passes_where_counting_cannot_decide(counting_clean_but_infeasible: Path) -> None:
    result = run("check", str(counting_clean_but_infeasible))
    assert result.exit_code == 0
    assert "No countable obstacles" in result.stdout
    assert "The solver has the final say" in result.stdout


def test_solve_reports_no_solution_with_its_own_exit_code(
    counting_clean_but_infeasible: Path,
) -> None:
    result = run("solve", str(counting_clean_but_infeasible))
    assert result.exit_code == 3
    assert "Status: INFEASIBLE" in result.stdout
    assert "No solution found (status INFEASIBLE)" in result.stdout


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
    result = run("explain", str(counting_clean_but_infeasible), str(out), "--dancer", "led0")
    assert result.exit_code == 0
    assert "Violated not-desired wishes:" in result.stdout
    assert "Respected not-desired wishes:" in result.stdout


def test_explain_a_dancer_whose_survey_holds_only_dislikes(solved: Path) -> None:
    result = run("explain", EXAMPLE, str(solved), "--dancer", "felix-w")
    assert result.exit_code == 0
    assert "No wishes fulfilled." in result.stdout
    assert "Respected not-desired wishes:" in result.stdout
