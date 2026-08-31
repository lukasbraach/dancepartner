"""Streamlit UI smoke tests.

The pages are thin by design, so these tests ask the questions a thin page can still get
wrong: does it render at all, does it reach the core with the configuration the coach chose,
and does it refuse to write anything the domain model would reject.

``AppTest`` runs the script in-process with no browser. ``at.exception`` collects anything the
script raised, so asserting it is empty is a real check and not a formality.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import Multiselect

from dancepartner.i18n import TABLES, Language, t
from dancepartner.model import Objective, Role, ScoreAggregation, Team
from dancepartner.storage import dump_team, load_team

from .builders import roster

REPO_ROOT = Path(__file__).resolve().parents[1]
HOME = str(REPO_ROOT / "app" / "Home.py")
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


PAGES = [
    "app/pages/team.py",
    "app/pages/survey.py",
    "app/pages/solution.py",
    "app/pages/analysis.py",
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


def test_solution_and_analysis_ask_for_a_solve_first() -> None:
    at = loaded(str(REPO_ROOT / "app" / "pages" / "analysis.py")).run()
    assert not at.exception
    assert t("ui.no_solution_yet") in texts(at)


# -- Home: loading ---------------------------------------------------------------------------


def test_home_loads_the_example_team() -> None:
    at = app().run()
    at.button[1].click().run()  # "Load example team"
    assert not at.exception

    team = at.session_state["team"]
    assert isinstance(team, Team)
    assert len(team.dancers) == 20
    # Freshly loaded matches the file, so there is nothing to warn about.
    assert at.session_state["dirty"] is False
    assert t("ui.unsaved") not in texts(at)


def test_home_reports_a_missing_file() -> None:
    at = app().run()
    at.text_input[0].set_value("/nope/missing.yaml").run()
    at.button[0].click().run()
    assert not at.exception
    assert "not found" in texts(at)


def test_home_reports_a_broken_team_file(tmp_path: Path) -> None:
    broken = tmp_path / "broken.yaml"
    broken.write_text("n_positions: 8\ndancers: [{id: a}]\n", encoding="utf-8")
    at = app().run()
    at.text_input[0].set_value(str(broken)).run()
    at.button[0].click().run()
    assert not at.exception
    assert "invalid" in texts(at) or "structure" in texts(at)


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


def test_home_saves_only_when_asked(tmp_path: Path) -> None:
    target = tmp_path / "saved.yaml"
    at = loaded(HOME).run()
    assert not target.exists(), "rendering the page must never write"

    at.text_input[-1].set_value(str(target)).run()
    at.button[-1].click().run()
    assert not at.exception
    assert target.exists()
    assert load_team(target).dancers == at.session_state["team"].dancers
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


def test_team_page_hint_names_the_ordering_rule() -> None:
    at = loaded(str(REPO_ROOT / "app" / "pages" / "team.py")).run()
    # Roster order is load-bearing -- symmetry breaking numbers positions by leader index --
    # so the page has to say so.
    assert t("ui.team.hint") in texts(at)


# -- Umfrage page -----------------------------------------------------------------------------


def test_survey_page_flags_a_dancer_named_in_both_directions() -> None:
    # A dancer with no survey yet, so each direction starts with exactly one empty tier.
    at = loaded(str(REPO_ROOT / "app" / "pages" / "survey.py")).run()
    at.selectbox[0].set_value("marie-g").run()
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
    at = loaded(str(REPO_ROOT / "app" / "pages" / "survey.py"), team=team).run()
    picked = at.selectbox[0].value
    assert picked not in at.multiselect[0].options
    assert len(at.multiselect[0].options) == len(team.dancers) - 1


# -- Lösung page ------------------------------------------------------------------------------


def test_solution_page_solves_and_shows_every_dancer_once() -> None:
    team = load_team(EXAMPLE)
    at = loaded(str(REPO_ROOT / "app" / "pages" / "solution.py"), team=team)
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
    at = loaded(str(REPO_ROOT / "app" / "pages" / "solution.py")).run()
    at.selectbox[0].set_value(Objective.WEIGHTED_SUM).run()
    assert at.session_state["config"].objective is Objective.WEIGHTED_SUM


def test_solution_page_passes_the_chosen_aggregation_to_the_solver() -> None:
    at = loaded(str(REPO_ROOT / "app" / "pages" / "solution.py")).run()
    default_config = at.session_state["config"]
    assert default_config.aggregation is ScoreAggregation.BEST
    at.selectbox[2].set_value(ScoreAggregation.SUM).run()
    chosen_config = at.session_state["config"]
    assert chosen_config.aggregation is ScoreAggregation.SUM


def test_solution_page_renders_a_neutral_dancer_grey_not_red() -> None:
    team = load_team(EXAMPLE)
    at = loaded(str(REPO_ROOT / "app" / "pages" / "solution.py"), team=team)
    at.run()
    at.button[0].click().run()
    assert not at.exception

    # marie-g submitted no survey: neutral gets the colourless marker, never a red one.
    neutral_name = team.dancers_by_id["marie-g"].name
    lines = texts(at).splitlines()
    marker = next(line for line in lines if neutral_name in line and line[0] in "⬜🟥🟨🟩")
    assert marker.startswith("⬜")


def test_solution_page_spells_no_vetoes_as_zero() -> None:
    at = loaded(str(REPO_ROOT / "app" / "pages" / "solution.py")).run()
    at.number_input[0].set_value(0).run()
    assert at.session_state["config"].veto_tier is None


# -- Analyse page -----------------------------------------------------------------------------


def solved_analysis() -> AppTest:
    """Run the Lösung page, then hand its result to the Analyse page."""
    team = load_team(EXAMPLE)
    solving = loaded(str(REPO_ROOT / "app" / "pages" / "solution.py"), team=team)
    solving.run()
    solving.number_input[1].set_value(FAST["max_solutions"]).run()
    solving.button[0].click().run()

    at = app(str(REPO_ROOT / "app" / "pages" / "analysis.py"))
    at.session_state["team"] = team
    at.session_state["result"] = solving.session_state["result"]
    at.session_state["config"] = solving.session_state["config"]
    return at.run()


def test_analysis_lists_the_unhappiest_dancer_first() -> None:
    at = solved_analysis()
    assert not at.exception

    result = at.session_state["result"]
    table = at.dataframe[0].value
    scores = list(table[t("table.col_score")])
    assert scores == sorted(scores), "the table must ascend -- unhappiest first"
    assert scores[0] == result.best.min_score
    assert len(scores) == len(at.session_state["team"].dancers)


def test_analysis_shows_absolute_satisfaction_percentages() -> None:
    at = solved_analysis()
    assert not at.exception

    table = at.dataframe[0].value
    column = list(table[t("ui.analysis.col_satisfaction")])
    numbers = [v for v in column if v is not None and v == v]  # NaN != NaN
    assert numbers, "somebody stated preferences"
    assert all(0 <= v <= 100 for v in numbers)
    assert 100 in numbers, "a fulfilled top-tier wish is exactly 100 %"
    # marie-g is neutral: her cell stays blank instead of claiming 0 %.
    assert len(numbers) < len(column)


def test_analysis_diffs_two_shortlist_entries_by_position_label() -> None:
    at = solved_analysis()
    result = at.session_state["result"]
    if len(result.solutions) < 2:
        pytest.skip("the example team produced a single optimum under this configuration")

    assert t("ui.analysis.shortlist_header") in texts(at)
    # The diff table names both labels; A-H, never a number.
    diff = at.dataframe[-1].value
    moved_from = list(diff[t("ui.analysis.col_from")])
    moved_to = list(diff[t("ui.analysis.col_to")])
    assert moved_from, "two distinct optima must differ somewhere"
    labels = set(at.session_state["team"].labels)
    for before, after in zip(moved_from, moved_to, strict=True):
        assert before != after
        assert {before, after} <= labels


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
    source = "\n".join(p.read_text(encoding="utf-8") for p in (REPO_ROOT / "app").rglob("*.py"))
    # The pages quote keys both ways: t("x") normally, t('x') inside an f-string.
    dynamic = ("ui.objective.", "ui.weights.", "ui.aggregation.", "ui.scope.")
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
