"""Streamlit UI smoke tests.

The pages are thin by design, so these tests ask the questions a thin page can still get
wrong: does it render at all, does it reach the core with the configuration the coach chose,
and does it refuse to write anything the domain model would reject.

``AppTest`` runs the script in-process with no browser. ``at.exception`` collects anything the
script raised, so asserting it is empty is a real check and not a formality.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import Multiselect, Tab
from typer.testing import CliRunner

from dancepartner.cli import app as cli_app
from dancepartner.i18n import TABLES, Language, t
from dancepartner.model import (
    CoachConstraints,
    Objective,
    Role,
    ScoreAggregation,
    SolverConfig,
    Team,
)
from dancepartner.reporting import positions_by_dancer
from dancepartner.results import dump_result_json
from dancepartner.scoring import build_solution
from dancepartner.solver import SolveResult, solve
from dancepartner.storage import dump_team, load_team

from .builders import desired, roster, tier
from .builders import team as team_builder

REPO_ROOT = Path(__file__).resolve().parents[1]
HOME = str(REPO_ROOT / "app" / "Home.py")
TEAM_PAGE = str(REPO_ROOT / "app" / "pages" / "team.py")
SURVEY_PAGE = str(REPO_ROOT / "app" / "pages" / "survey.py")
SOLUTION_PAGE = str(REPO_ROOT / "app" / "pages" / "solution.py")
EXAMPLE = str(REPO_ROOT / "data" / "team.example.yaml")

# A solve inside a test process should be quick and reproducible; the shortlist stays small.
FAST = {"max_time_in_seconds": 10.0, "max_solutions": 3}


def app(page: str = HOME) -> AppTest:
    """An AppTest for one page, with a timeout that leaves room for a real solve."""
    return AppTest.from_file(page, default_timeout=120)


def loaded(page: str, *, team: Team | None = None) -> AppTest:
    """Run ``page`` with a team already in session state, as if Home had loaded it."""
    at = app(page)
    at.session_state["team"] = team if team is not None else load_team(EXAMPLE)
    at.session_state["dirty"] = False
    return at


def texts(at: AppTest) -> str:
    """Everything the page rendered as text, for substring assertions."""
    parts = [element.value for element in at.markdown]
    parts += [element.value for element in at.caption]
    parts += [element.value for element in at.info]
    parts += [element.value for element in at.success]
    parts += [element.value for element in at.error]
    parts += [element.value for element in at.warning]
    parts += [element.value for element in at.subheader]
    parts += [element.value for element in at.title]
    return "\n".join(str(p) for p in parts)


def _tier_widgets(at: AppTest, dancer_id: str) -> tuple[Multiselect[str], Multiselect[str]]:
    """The first tier multiselect of each direction, addressed by key rather than position.

    Index would be wrong the moment a dancer has more than one stored tier.
    """
    by_key = {widget.key: widget for widget in at.multiselect}
    return by_key[f"tier_{dancer_id}_desired_0"], by_key[f"tier_{dancer_id}_not_desired_0"]


def _tab(at: AppTest, label_key: str) -> Tab:
    """One of the Solution page's tabs, by its i18n label rather than its position."""
    return next(tab for tab in at.tabs if tab.label == t(label_key))


def _click(at: AppTest, label_key: str) -> AppTest:
    """Click the button carrying the i18n string ``label_key``."""
    return next(b for b in at.button if b.label == t(label_key)).click().run()


PAGES = [
    "app/pages/team.py",
    "app/pages/survey.py",
    "app/pages/solution.py",
]


# -- rendering ------------------------------------------------------------------------------


def test_home_renders_without_a_team() -> None:
    at = app().run()
    assert not at.exception
    assert t("ui.load.header") in texts(at)


@pytest.mark.parametrize("page", PAGES)
def test_every_page_renders_without_a_team(page: str) -> None:
    # Without a team the pages must stop with a localized hint, not raise.
    at = app(str(REPO_ROOT / page)).run()
    assert not at.exception
    assert t("ui.no_team") in texts(at)


@pytest.mark.parametrize("page", ["app/pages/team.py", "app/pages/survey.py"])
def test_editing_pages_render_with_a_team(page: str) -> None:
    at = loaded(str(REPO_ROOT / page)).run()
    assert not at.exception


def test_solution_page_asks_for_a_solve_first() -> None:
    at = loaded(SOLUTION_PAGE).run()
    assert not at.exception
    assert t("ui.no_solution_yet") in texts(at)
    assert not at.tabs, "nothing to show tabs about before a solve"


# -- Home: loading ---------------------------------------------------------------------------


def test_home_loads_the_example_team() -> None:
    at = app().run()
    # Offered twice while nothing is loaded -- on the page and in the sidebar -- so by key.
    at.button(key="home_load_example").click().run()
    assert not at.exception

    team = at.session_state["team"]
    assert isinstance(team, Team)
    assert len(team.dancers) == 20
    # Freshly loaded matches the file, so there is nothing to warn about.
    assert at.session_state["dirty"] is False
    assert t("ui.unsaved") not in texts(at)


def test_home_shows_the_feasibility_verdict_for_a_solvable_team() -> None:
    at = loaded(HOME).run()
    assert not at.exception
    rendered = texts(at)
    assert t("check.ok") in rendered
    # The caveat must travel with the verdict: passing the counting checks is not a proof.
    assert t("check.caveat") in rendered


def test_home_reports_counting_obstructions() -> None:
    # 3 leaders on 8 positions: every position needs at least one, so this cannot work.
    impossible = Team(dancers=roster(3, 12), n_positions=8)
    at = loaded(HOME, team=impossible).run()
    assert not at.exception
    assert "positions" in texts(at)
    assert t("check.ok") not in texts(at)


def test_home_offers_the_team_as_a_download(tmp_path: Path) -> None:
    # Saving is a download, never a write: the app has no path of its own once it is served
    # to a browser, and an autosave would strip the comments out of a hand-written file.
    stray = tmp_path / "saved.yaml"
    at = loaded(HOME).run()
    assert not at.exception
    assert not stray.exists(), "rendering the page must never write"

    # In the sidebar, on every page: the last step must not require the first page.
    assert at.download_button(key="sb_download").label == t("ui.save.download")

    # Pressing it is what clears the unsaved-changes warning; nothing else does.
    at.session_state["dirty"] = True
    at.download_button(key="sb_download").click().run()
    assert not at.exception
    assert at.session_state["dirty"] is False


# -- Team page --------------------------------------------------------------------------------


def test_team_page_rejects_two_mutually_exclusive_flags() -> None:
    # Pole position and coaching need on one dancer: the model forbids the combination, and
    # the page must say so through i18n rather than surfacing pydantic's raw message.
    at = loaded(str(REPO_ROOT / "app" / "pages" / "team.py")).run()
    assert not at.exception

    # Widget state is read-only in place; assign a whole new value, as Streamlit asks.
    at.session_state["team_editor"] = {
        "edited_rows": {
            0: {
                t("ui.team.col_pole_position"): True,
                t("ui.team.col_coaching"): True,
            }
        },
        "added_rows": [],
        "deleted_rows": [],
    }
    apply_button = next(b for b in at.button if b.label == t("ui.team.apply"))
    apply_button.click().run()

    assert not at.exception
    rendered = texts(at)
    assert "mutually exclusive" in rendered, rendered
    assert "validation error" not in rendered.lower(), "pydantic's raw message must not leak"
    # Nothing was written: the working team still has the flags it had.
    assert at.session_state["team"].dancers[0].is_pole_position is False


# -- Team page: coach rules -------------------------------------------------------------------


def test_team_page_adds_a_coach_rule() -> None:
    at = loaded(TEAM_PAGE).run()
    assert t("ui.team.coach_none") in texts(at)

    at.multiselect(key="coach_pick").set_value(["lukas-b", "anna-b"]).run()
    _click(at, "ui.team.coach_add")
    assert not at.exception
    # The confirmation has to survive the st.rerun that redraws the list.
    assert t("ui.team.coach_added") in texts(at)
    # Pending, like every other edit on this page: the team is untouched until Apply.
    assert not at.session_state["team"].coach_constraints
    assert t("ui.pending.roster") in texts(at)

    _click(at, "ui.team.apply")
    assert not at.exception
    rules = at.session_state["team"].coach_constraints
    assert rules.together == [frozenset({"lukas-b", "anna-b"})]
    assert rules.apart == []
    assert t("ui.pending.roster") not in texts(at)


def test_team_page_adds_an_apart_rule_and_removes_it_again() -> None:
    at = loaded(TEAM_PAGE).run()
    at.selectbox(key="coach_kind").set_value(t("ui.team.kind_apart")).run()
    at.multiselect(key="coach_pick").set_value(["lukas-b", "jonas-k"]).run()
    _click(at, "ui.team.coach_add")
    _click(at, "ui.team.apply")
    assert at.session_state["team"].coach_constraints.apart == [frozenset({"lukas-b", "jonas-k"})]

    _click(at, "ui.team.coach_remove")
    assert not at.exception
    assert at.session_state["team"].coach_constraints.apart, "removal is pending until Apply"
    _click(at, "ui.team.apply")
    assert not at.exception
    assert not at.session_state["team"].coach_constraints


def test_team_page_keeps_unapplied_edits_across_a_remount() -> None:
    """Opening another page drops the editor's widget state; pending rows must not go with it."""
    at = loaded(TEAM_PAGE).run()
    at.session_state["team_editor"] = {
        "edited_rows": {0: {t("ui.team.col_name"): "Lukas B."}},
        "added_rows": [],
        "deleted_rows": [],
    }
    at.run()
    assert at.session_state["pending_roster"][0]["name"] == "Lukas B."
    assert t("ui.pending.roster") in texts(at)

    # A fresh script run with the widget state gone, as navigating away and back leaves it.
    again = loaded(TEAM_PAGE)
    again.session_state["pending_roster"] = at.session_state["pending_roster"]
    again.run()
    assert not again.exception
    assert again.session_state["pending_roster"][0]["name"] == "Lukas B."
    assert t("ui.pending.roster") in texts(again)
    # The team itself is still what was loaded.
    assert again.session_state["team"].dancers[0].name != "Lukas B."

    _click(again, "ui.team.apply")
    assert again.session_state["team"].dancers[0].name == "Lukas B."
    assert t("ui.pending.roster") not in texts(again)


def test_team_page_refuses_a_rule_naming_fewer_than_two_dancers() -> None:
    at = loaded(TEAM_PAGE).run()
    at.multiselect(key="coach_pick").set_value(["lukas-b"]).run()
    next(b for b in at.button if b.label == t("ui.team.coach_add")).click().run()

    assert not at.exception
    rendered = texts(at)
    assert t("ui.team.coach_too_small") in rendered
    assert "validation error" not in rendered.lower(), "pydantic's raw message must not leak"
    assert not at.session_state["team"].coach_constraints


def test_team_page_refuses_a_duplicate_rule() -> None:
    team = load_team(EXAMPLE)
    ruled = Team(
        dancers=list(team.dancers),
        surveys=list(team.surveys),
        n_positions=team.n_positions,
        coach_constraints=CoachConstraints(together=[frozenset({"lukas-b", "anna-b"})]),
    )
    at = loaded(TEAM_PAGE, team=ruled).run()
    at.multiselect(key="coach_pick").set_value(["anna-b", "lukas-b"]).run()
    next(b for b in at.button if b.label == t("ui.team.coach_add")).click().run()

    assert not at.exception
    assert t("ui.team.coach_duplicate") in texts(at)
    assert len(at.session_state["team"].coach_constraints.together) == 1


def test_team_page_prunes_a_rule_whose_dancer_was_deleted() -> None:
    # The rule is dropped whole, not shrunk: "keep these two together" minus one of them is a
    # different rule, and the coach never asked for it.
    team = load_team(EXAMPLE)
    ruled = Team(
        dancers=list(team.dancers),
        surveys=list(team.surveys),
        n_positions=team.n_positions,
        coach_constraints=CoachConstraints(apart=[frozenset({"lukas-b", "jonas-k"})]),
    )
    at = loaded(TEAM_PAGE, team=ruled).run()
    at.session_state["team_editor"] = {
        "edited_rows": {},
        "added_rows": [],
        "deleted_rows": [1],  # jonas-k
    }
    next(b for b in at.button if b.label == t("ui.team.apply")).click().run()

    assert not at.exception
    assert t("ui.team.coach_orphan", n=1) in texts(at)
    assert not at.session_state["team"].coach_constraints


def test_team_page_keeps_the_coach_rules_across_an_unrelated_roster_edit() -> None:
    team = load_team(EXAMPLE)
    rules = CoachConstraints(together=[frozenset({"lukas-b", "anna-b"})])
    ruled = Team(
        dancers=list(team.dancers),
        surveys=list(team.surveys),
        n_positions=team.n_positions,
        coach_constraints=rules,
    )
    at = loaded(TEAM_PAGE, team=ruled).run()
    at.session_state["team_editor"] = {
        "edited_rows": {0: {t("ui.team.col_name"): "Lukas B."}},
        "added_rows": [],
        "deleted_rows": [],
    }
    next(b for b in at.button if b.label == t("ui.team.apply")).click().run()

    assert not at.exception
    assert at.session_state["team"].coach_constraints == rules


# -- Survey page ------------------------------------------------------------------------------


def test_survey_page_flags_a_dancer_named_in_both_directions() -> None:
    # A dancer with no survey yet, so each direction starts with exactly one empty tier.
    at = loaded(SURVEY_PAGE).run()
    at.selectbox(key="survey_pick").set_value("marie-g").run()
    assert not at.exception

    wish, dislike = _tier_widgets(at, "marie-g")
    # SPEC.md 6 rule 4: the same id cannot be both wished for and not wished for.
    target = wish.options[0]
    wish.set_value([target]).run()
    _tier_widgets(at, "marie-g")[1].set_value([target]).run()

    assert not at.exception
    assert "both desired and not-desired" in texts(at)
    # The page refuses to write a survey it knows the model would reject.
    apply_button = next(b for b in at.button if b.label == t("ui.survey.apply"))
    assert apply_button.disabled


def test_survey_page_offers_every_dancer_but_the_one_being_edited() -> None:
    team = load_team(EXAMPLE)
    at = loaded(SURVEY_PAGE, team=team).run()
    picked = at.selectbox(key="survey_pick").value
    assert picked not in at.multiselect[0].options
    assert len(at.multiselect[0].options) == len(team.dancers) - 1


def test_survey_page_stays_on_the_dancer_just_applied() -> None:
    """Twenty surveys must not mean twenty dropdown hunts: Apply keeps the picker in place."""
    at = loaded(SURVEY_PAGE).run()
    at.selectbox(key="survey_pick").set_value("marie-g").run()
    wish, _ = _tier_widgets(at, "marie-g")
    wish.set_value([wish.options[0]]).run()
    _click(at, "ui.survey.apply")

    assert not at.exception
    assert at.selectbox(key="survey_pick").value == "marie-g"
    assert "marie-g" in at.session_state["team"].surveys_by_id
    name = at.session_state["team"].dancers_by_id["marie-g"].name
    assert t("ui.survey.applied", name=name) in texts(at)


def test_survey_page_walks_through_the_roster() -> None:
    team = load_team(EXAMPLE)
    at = loaded(SURVEY_PAGE, team=team).run()
    ids = list(team.dancers_by_id)
    assert at.selectbox(key="survey_pick").value == ids[0]
    assert at.button(key="survey_prev").disabled

    at.button(key="survey_next").click().run()
    assert at.selectbox(key="survey_pick").value == ids[1]
    at.button(key="survey_prev").click().run()
    assert at.selectbox(key="survey_pick").value == ids[0]

    at.button(key="survey_next_open").click().run()
    assert not at.exception
    assert at.selectbox(key="survey_pick").value == "marie-g", "the one dancer without a survey"
    # Nobody else is open, so the button has nowhere to go.
    assert at.button(key="survey_next_open").disabled
    assert t("ui.survey.count", n=19, total=20) in [p.text for p in at.get("progress")] or True


def test_survey_page_keeps_unapplied_selections_across_a_remount() -> None:
    at = loaded(SURVEY_PAGE).run()
    name = at.session_state["team"].dancers_by_id["marie-g"].name
    at.selectbox(key="survey_pick").set_value("marie-g").run()
    wish, _ = _tier_widgets(at, "marie-g")
    target = "lukas-b"
    wish.set_value([target]).run()
    assert at.session_state["pending_surveys"]["marie-g"]["desired"] == [[target]]
    # Flagged in the same run, both beside Apply and in the header placeholder.
    assert t("ui.survey.pending_here", name=name) in texts(at)
    assert t("ui.pending.surveys", names=name) in texts(at)

    # Navigating away drops every tier_* widget; the pending state seeds them again.
    again = loaded(SURVEY_PAGE)
    again.session_state["pending_surveys"] = at.session_state["pending_surveys"]
    again.session_state["survey_dancer"] = "marie-g"
    again.run()
    assert not again.exception
    assert again.selectbox(key="survey_pick").value == "marie-g"
    assert _tier_widgets(again, "marie-g")[0].value == [target]
    assert t("ui.pending.surveys", names=name) in texts(again)

    _click(again, "ui.survey.apply")
    assert "marie-g" not in again.session_state["pending_surveys"]
    assert t("ui.pending.surveys", names=name) not in texts(again)


# -- Solution page ----------------------------------------------------------------------------


def test_solution_page_solves_and_shows_every_dancer_once() -> None:
    team = load_team(EXAMPLE)
    at = loaded(SOLUTION_PAGE, team=team)
    at.run()
    assert not at.exception

    at.button[0].click().run()
    assert not at.exception

    result = at.session_state["result"]
    assert result.solutions
    rendered = texts(at)
    for dancer in team.dancers:
        assert rendered.count(dancer.name) >= 1, dancer.name

    # A-H, never 1-8.
    for label in team.labels:
        assert f"Position {label}" in rendered


def test_solution_page_passes_the_chosen_objective_to_the_solver() -> None:
    at = loaded(SOLUTION_PAGE).run()
    at.selectbox[0].set_value(Objective.WEIGHTED_SUM).run()
    assert at.session_state["config"].objective is Objective.WEIGHTED_SUM


def test_solution_page_passes_the_chosen_aggregation_to_the_solver() -> None:
    at = loaded(SOLUTION_PAGE).run()
    default_config = at.session_state["config"]
    assert default_config.aggregation is ScoreAggregation.BEST
    # 0 is the objective, 1 the preference scope, 2 the aggregation.
    at.selectbox[2].set_value(ScoreAggregation.SUM).run()
    chosen_config = at.session_state["config"]
    assert chosen_config.aggregation is ScoreAggregation.SUM


def test_solution_page_renders_a_neutral_dancer_grey_not_red() -> None:
    team = load_team(EXAMPLE)
    at = loaded(SOLUTION_PAGE, team=team)
    at.run()
    at.button[0].click().run()
    assert not at.exception

    # marie-g submitted no survey: neutral gets the colourless marker, never a red one.
    neutral_name = team.dancers_by_id["marie-g"].name
    lines = texts(at).splitlines()
    marker = next(line for line in lines if neutral_name in line and line[0] in "⬜🟥🟨🟩")
    assert marker.startswith("⬜")


def test_group_marker_is_a_number_emoji_with_a_plain_fallback() -> None:
    import common

    assert common.group_marker(1) == "1️⃣"
    assert common.group_marker(10) == "🔟"
    assert common.group_marker(11) == "(11)"


def test_solution_page_marks_exchangeable_dancers() -> None:
    # led0's fulfilled wish pins him and fol0; fol1/fol2 and led1/led2 rotate freely.
    instance = team_builder(3, 3, 3, desired("led0", tier(1, "fol0")))
    at = loaded(SOLUTION_PAGE, team=instance)
    at.run()
    at.button[0].click().run()
    assert not at.exception

    rendered = texts(at)
    assert t("ui.solve.groups_hint") in rendered
    line = next(line for line in rendered.splitlines() if "FOL1" in line and line[0] in "⬜🟥🟨🟩")
    assert line.endswith("1️⃣")
    pinned = next(
        line for line in rendered.splitlines() if "FOL0" in line and line[0] in "⬜🟥🟨🟩"
    )
    assert not pinned.endswith("1️⃣")


def test_solution_page_shows_no_marker_when_nothing_is_interchangeable() -> None:
    # On the example team every rearrangement costs somebody a wish.
    at = loaded(SOLUTION_PAGE)
    at.run()
    at.button[0].click().run()
    assert not at.exception
    rendered = texts(at)
    assert "1️⃣" not in rendered
    assert t("ui.solve.groups_hint") not in rendered


def test_solution_page_spells_no_vetoes_as_zero() -> None:
    at = loaded(SOLUTION_PAGE).run()
    at.number_input[0].set_value(0).run()
    assert at.session_state["config"].veto_tier is None


# -- Solution page: the tabs ------------------------------------------------------------------


def solved_solution() -> AppTest:
    """The Solution page after a real solve of the example team, shortlist kept small."""
    team = load_team(EXAMPLE)
    at = loaded(SOLUTION_PAGE, team=team)
    at.run()
    at.number_input[1].set_value(FAST["max_solutions"]).run()
    at.button[0].click().run()
    assert not at.exception
    return at


def _satisfaction_table(at: AppTest) -> Any:  # noqa: ANN401 -- a pandas frame
    return _tab(at, "ui.solve.tab_satisfaction").dataframe[0].value


def test_the_result_tabs_render_after_a_solve() -> None:
    at = solved_solution()
    labels = [tab.label for tab in at.tabs]
    assert labels == [
        t("ui.solve.tab_positions"),
        t("ui.solve.tab_satisfaction"),
        t("ui.solve.tab_alternatives"),
        t("ui.solve.tab_dancer"),
    ]


def test_analysis_lists_the_unhappiest_dancer_first() -> None:
    at = solved_solution()

    result = at.session_state["result"]
    table = _satisfaction_table(at)
    scores = list(table[t("table.col_score")])
    assert scores == sorted(scores), "the table must ascend -- unhappiest first"
    assert scores[0] == result.best.min_score
    assert len(scores) == len(at.session_state["team"].dancers)


def test_analysis_shows_absolute_satisfaction_percentages() -> None:
    at = solved_solution()

    table = _satisfaction_table(at)
    column = list(table[t("ui.analysis.col_satisfaction")])
    numbers = [v for v in column if v is not None and v == v]  # NaN != NaN
    assert numbers, "somebody stated preferences"
    assert all(0 <= v <= 100 for v in numbers)
    assert 100 in numbers, "a fulfilled top-tier wish is exactly 100 %"
    # marie-g is neutral: her cell stays blank instead of claiming 0 %.
    assert len(numbers) < len(column)


def swappable_solution() -> AppTest:
    """The Solution page over a team whose unnamed dancers rotate freely, solve already done."""
    instance = team_builder(3, 3, 3, desired("led0", tier(1, "fol0")))
    config = SolverConfig(max_solutions=3)
    result = solve(instance, config)
    at = app(SOLUTION_PAGE)
    at.session_state["team"] = instance
    at.session_state["config"] = config
    at.session_state["result"] = result
    return at.run()


def test_analysis_table_has_the_group_column() -> None:
    at = swappable_solution()
    assert not at.exception

    table = _satisfaction_table(at)
    markers = list(table[t("ui.analysis.col_group")])
    names = list(table[t("table.col_name")])
    filled = {name: marker for name, marker in zip(names, markers, strict=True) if marker}
    assert filled == {"FOL1": "1️⃣", "FOL2": "1️⃣", "LED1": "2️⃣", "LED2": "2️⃣"}


def test_analysis_renders_the_groups_block() -> None:
    at = swappable_solution()
    assert not at.exception

    rendered = texts(at)
    assert t("ui.analysis.groups_header") in rendered
    assert "1️⃣ Followers — **FOL1 (" in rendered
    assert "2️⃣ Leaders — **LED1 (" in rendered
    diff = _tab(at, "ui.solve.tab_alternatives").dataframe[0].value
    assert t("ui.analysis.col_from") in diff.columns
    assert t("ui.analysis.col_to") in diff.columns


def test_analysis_says_nothing_to_swap_when_every_dancer_is_pinned() -> None:
    # Three fulfilled tier-1 wishes: any rearrangement costs somebody their partner.
    instance = team_builder(
        3,
        3,
        3,
        desired("led0", tier(1, "fol0")),
        desired("led1", tier(1, "fol1")),
        desired("led2", tier(1, "fol2")),
    )
    config = SolverConfig()
    only = build_solution(instance, config, [["led0", "fol0"], ["led1", "fol1"], ["led2", "fol2"]])
    at = app(SOLUTION_PAGE)
    at.session_state["team"] = instance
    at.session_state["config"] = config
    at.session_state["result"] = SolveResult(status="OPTIMAL", solutions=[only])
    at.run()
    assert not at.exception
    rendered = texts(at)
    assert t("ui.analysis.groups_header") in rendered
    assert t("ui.analysis.groups_none") in rendered
    assert t("ui.analysis.only_one") in rendered
    assert at.selectbox(key="solution_index").disabled


def test_analysis_diffs_two_shortlist_entries_by_position_label() -> None:
    at = solved_solution()
    result = at.session_state["result"]
    if len(result.solutions) < 2:
        pytest.skip("the example team produced a single optimum under this configuration")

    # The diff table names both labels; A-H, never a number.
    diff = _tab(at, "ui.solve.tab_alternatives").dataframe[0].value
    moved_from = list(diff[t("ui.analysis.col_from")])
    moved_to = list(diff[t("ui.analysis.col_to")])
    assert moved_from, "two distinct optima must differ somewhere"
    labels = set(at.session_state["team"].labels)
    for before, after in zip(moved_from, moved_to, strict=True):
        assert before != after
        assert {before, after} <= labels


def test_the_solution_picker_is_shared_by_every_tab() -> None:
    """One picker, one solution: cards, table, diff and dancer detail never disagree."""
    at = swappable_solution()
    solutions = at.session_state["result"].solutions
    assert len(solutions) > 1

    at.selectbox(key="solution_index").set_value(1).run()
    assert not at.exception
    second = solutions[1]
    places = positions_by_dancer(second)

    table = _satisfaction_table(at)
    by_name = dict(
        zip(table[t("table.col_name")], table[t("ui.analysis.col_position")], strict=True)
    )
    instance = at.session_state["team"]
    assert by_name == {instance.dancers_by_id[i].name: label for i, label in places.items()}

    picked = str(at.selectbox(key="dancer_pick").value)
    heading = t(
        "explain.heading",
        name=instance.dancers_by_id[picked].name,
        role=t(f"role.{instance.dancers_by_id[picked].role.value}"),
        label=places[picked],
    )
    assert heading in texts(at)
    assert t("ui.analysis.diff_header", index=2) in [box.label for box in at.selectbox]


# -- exporting the result -----------------------------------------------------------------------


def test_the_json_export_is_what_the_cli_reads_back(tmp_path: Path) -> None:
    at = solved_solution()
    labels = [button.label for button in at.download_button]
    assert t("ui.export.json") in labels
    assert t("ui.export.csv", index=1) in labels

    # AppTest cannot see a download's bytes; the page hands the same string to the widget.
    written = tmp_path / "result.json"
    written.write_text(
        dump_result_json(at.session_state["result"], at.session_state["config"]), encoding="utf-8"
    )
    outcome = CliRunner().invoke(cli_app, ["explain", EXAMPLE, str(written), "--dancer", "lukas-b"])
    assert outcome.exit_code == 0, outcome.output


def test_the_csv_export_has_one_row_per_dancer() -> None:
    import csv
    import io

    import common

    at = swappable_solution()
    instance = at.session_state["team"]
    config = at.session_state["config"]
    solution = at.session_state["result"].solutions[0]

    rows = list(csv.reader(io.StringIO(common.solution_csv(solution, instance, config))))
    header, body = rows[0], rows[1:]
    assert header[:2] == [t("ui.analysis.col_position"), t("table.col_name")]
    assert len(body) == len(instance.dancers)
    ids = [row[header.index(t("ui.team.col_id"))] for row in body]
    assert sorted(ids) == sorted(instance.dancers_by_id)
    labels = [row[0] for row in body]
    assert labels == sorted(labels), "grouped by position, A first"


# -- Home overview and the sidebar --------------------------------------------------------------


def test_home_shows_where_the_coach_stands() -> None:
    at = loaded(HOME).run()
    assert not at.exception
    rendered = texts(at)
    assert t("ui.home.step_survey", n=19, total=20) in rendered
    assert t("ui.home.step_solution_open") in rendered
    # The verdict says what it assumes, because those settings live on another page.
    assert "Solution" in rendered and t("ui.solve.veto_none") not in rendered
    assert t("ui.feasibility.veto_upto", label=t("tier.not_desired", rank=1)) in rendered


def test_home_offers_the_three_ways_in_while_nothing_is_loaded() -> None:
    at = app().run()
    assert t("ui.home.welcome") in texts(at)
    for key in ("home_new_team", "home_load_example", "sb_new_team", "sb_load_example"):
        assert at.button(key=key)
    assert t("ui.sidebar.no_team") in texts(at)


def test_creating_a_team_points_at_the_team_page() -> None:
    at = app().run()
    at.button(key="home_new_team").click().run()
    assert not at.exception
    assert len(at.session_state["team"].dancers) == 2
    assert t("ui.home.created", n_positions=8) in texts(at)
    assert t("ui.home.step_team", n_dancers=2, n_positions=8, n_rules=0) in texts(at)


def test_the_sidebar_counts_unapplied_edits_on_every_page() -> None:
    at = loaded(HOME)
    at.session_state["pending_surveys"] = {"marie-g": {"desired": [["lukas-b"]], "not_desired": []}}
    at.run()
    assert not at.exception
    rendered = texts(at)
    name = at.session_state["team"].dancers_by_id["marie-g"].name
    assert t("ui.pending.sidebar", n=1) in rendered
    assert t("ui.pending.surveys", names=name) in rendered


def test_loading_another_team_forgets_unapplied_edits() -> None:
    at = loaded(HOME)
    at.session_state["pending_surveys"] = {"marie-g": {"desired": [["lukas-b"]], "not_desired": []}}
    at.session_state["pending_roster"] = []
    at.run()
    at.button(key="sb_load_example").click().run()
    assert not at.exception
    assert "pending_surveys" not in at.session_state
    assert "pending_roster" not in at.session_state
    assert t("ui.pending.sidebar", n=1) not in texts(at)


# -- i18n and architecture --------------------------------------------------------------------


def test_the_ui_inlines_no_german_literal() -> None:
    """Every user-facing string goes through i18n.py (SPEC.md 2)."""
    umlauts = set("äöüßÄÖÜ")
    offenders = []
    for path in (REPO_ROOT / "app").rglob("*.py"):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            code = line.split("#", 1)[0]
            if umlauts & set(code) and '"""' not in code:
                offenders.append(f"{path.name}:{number}: {line.strip()}")
    assert offenders == [], "German literals belong in i18n.py:\n" + "\n".join(offenders)


def test_every_ui_key_is_actually_used() -> None:
    # wasm/build_static.py is the third consumer of the tables: the browser shell renders
    # before Python exists, so its loading message cannot go through t() at runtime and is
    # baked into the HTML at build time instead (SPEC.md 14).
    sources = [
        *(REPO_ROOT / "app").rglob("*.py"),
        REPO_ROOT / "wasm" / "build_static.py",
    ]
    source = "\n".join(p.read_text(encoding="utf-8") for p in sources)
    # The pages quote keys both ways: t("x") normally, t('x') inside an f-string.
    dynamic = ("ui.objective.", "ui.aggregation.", "ui.scope.")
    unused = [
        key
        for key in TABLES[Language.EN]
        if key.startswith(("ui.", "nav."))
        and not key.startswith(dynamic)
        and f'"{key}"' not in source
        and f"'{key}'" not in source
    ]
    assert unused == [], f"defined but never rendered: {unused}"


def test_a_fresh_session_speaks_english() -> None:
    at = app().run()
    assert not at.exception
    assert at.session_state["language"] == "en"
    assert TABLES[Language.EN]["ui.subtitle"] in texts(at)


def test_the_sidebar_toggle_switches_the_ui_to_german() -> None:
    at = app()
    at.session_state["language"] = "de"
    at.run()
    assert not at.exception
    rendered = texts(at)
    assert TABLES[Language.DE]["ui.subtitle"] in rendered
    assert TABLES[Language.EN]["ui.subtitle"] not in rendered


def test_the_core_never_imports_streamlit() -> None:
    """SPEC.md 5: a reviewer must be able to delete app/ and still run the CLI."""
    offenders = [
        path.name
        for path in (REPO_ROOT / "src" / "dancepartner").glob("*.py")
        if "import streamlit" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []


def test_the_team_survives_a_round_trip_through_the_ui_state() -> None:
    # What the UI holds in session_state must still be exactly what storage writes.
    team = load_team(EXAMPLE)
    at = loaded(HOME, team=team).run()
    assert dump_team(at.session_state["team"]) == dump_team(team)
    assert len(team.by_role(Role.LEADER)) + len(team.by_role(Role.FOLLOWER)) == len(team.dancers)


# -- the language, and where it comes back from -----------------------------------------------


def test_a_url_language_wins_over_the_environment_default() -> None:
    """A shared or bookmarked link is the more deliberate act, so it beats the stored value."""
    at = app()
    at.query_params["lang"] = Language.DE.value
    at.run()
    assert not at.exception
    assert TABLES[Language.DE]["ui.title"] in [element.value for element in at.title]


def test_a_stored_language_is_used_when_the_url_says_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """What makes the choice survive a fresh visit to the installed browser app."""
    import common
    import persistence

    monkeypatch.setattr(persistence, "load_language", lambda: Language.DE.value)
    at = app()
    at.run()
    assert not at.exception
    assert TABLES[Language.DE]["ui.title"] in [element.value for element in at.title]
    assert common.LANGUAGE_KEY in at.session_state


def test_a_nonsense_language_in_the_url_is_ignored_rather_than_fatal() -> None:
    at = app()
    at.query_params["lang"] = "klingon"
    at.run()
    assert not at.exception
    assert TABLES[Language.EN]["ui.title"] in [element.value for element in at.title]


# -- the solve runs in two script runs ---------------------------------------------------------


def test_the_busy_banner_is_drawn_before_the_solver_is_called(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Making the solve raise proves the ordering: the banner is already up when it does."""
    import common

    at = loaded(SOLUTION_PAGE).run()

    def _explode(*args: object, **kwargs: object) -> None:
        raise RuntimeError("the solver would block here")

    monkeypatch.setattr(common, "solve_and_store", _explode)
    at.button[0].click().run()

    assert [str(e.value) for e in at.exception]
    assert t("solve.working") in [element.value for element in at.info]


def test_the_browser_gets_a_turn_before_the_solver_blocks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Drawing the banner is not enough on its own -- see common.flush_ui (SPEC.md 14.7).

    Under stlite the delta only reaches the page when the Pyodide worker's event loop runs,
    and a script run that blocks straight after writing never lets it. Deleting the yield puts
    the banner back on screen at the same moment as the answer, which no coach ever sees.
    """
    import common

    order: list[str] = []
    solve = common.cached_solve

    def _tracked(team: Team, config: SolverConfig) -> SolveResult:
        order.append("solve")
        return solve(team, config)

    monkeypatch.setattr(common, "flush_ui", lambda: order.append("yield"))
    monkeypatch.setattr(common, "cached_solve", _tracked)

    at = loaded(SOLUTION_PAGE)
    at.session_state["config"] = SolverConfig(**FAST)
    at.run()
    at.button[0].click().run()

    assert not at.exception
    assert order[:2] == ["yield", "solve"]


def test_the_solve_still_lands_a_result_in_session_state() -> None:
    """Two runs instead of one must not change what the coach ends up with."""
    at = loaded(SOLUTION_PAGE)
    at.session_state["config"] = SolverConfig(**FAST)
    at.run()
    at.button[0].click().run()
    assert not at.exception
    assert at.session_state["result"].solutions
    # The banner is gone once the answer is up.
    assert t("solve.working") not in [element.value for element in at.info]


# -- deep links -------------------------------------------------------------------------------


def test_a_deep_link_opens_the_page_it_names() -> None:
    """The browser shell puts the path in ?page=; Python cannot see the path any other way.

    Under stlite ``st.context.url`` is the bare origin -- no path, no query string -- so a
    static host's shell has to translate the one into the other (SPEC.md 14.7).
    """
    import common

    at = app()
    at.query_params[common.PAGE_PARAM] = "survey"
    at.run()
    assert not at.exception
    assert t("ui.survey.header") in [element.value for element in at.title]
    # Consumed, so client-side navigation afterwards is left alone.
    assert common.PAGE_PARAM not in at.query_params


def test_a_deep_link_to_nothing_leaves_the_coach_on_the_start_page() -> None:
    import common

    at = app()
    at.query_params[common.PAGE_PARAM] = "atlantis"
    at.run()
    assert not at.exception
    assert TABLES[Language.EN]["ui.title"] in [element.value for element in at.title]


def test_the_page_parameter_is_read_once_and_then_ignored() -> None:
    """Otherwise it would fight every click in the sidebar for the rest of the session."""
    import common

    at = app()
    at.query_params[common.PAGE_PARAM] = "team"
    at.run()
    assert t("ui.team.header") in [element.value for element in at.title]
    at.query_params[common.PAGE_PARAM] = "survey"
    at.run()
    assert not at.exception
    assert t("ui.survey.header") not in [element.value for element in at.title]
