"""Streamlit entry point: declares the navigation, draws the sidebar workspace, renders Home.

Run with ``streamlit run app/Home.py`` from the repository root.

The page modules are ``pages/team.py``, ``pages/survey.py`` and ``pages/solution.py`` -- English
names per the language policy in SPEC.md 2, and no numeric prefixes. Going through
``st.navigation`` puts the sidebar labels in ``i18n.py`` where every other user-facing string
lives, the page list below fixes the order, and ``1_Team`` would not be a valid module name for
``mypy --strict`` anyway.

Home itself is an overview, not the place things happen: where the coach stands in the three
steps, and the pre-check. Loading and saving live in the sidebar, on every page (SPEC.md 10).
"""

from __future__ import annotations

import streamlit as st

import common
from dancepartner.i18n import t
from dancepartner.model import Role, SolverConfig, Team

common.sync_language()
# st.navigation runs this file on every rerun whichever page is showing, so this one call
# covers all four pages (SPEC.md 14.4). It is a no-op once a team is loaded.
common.restore_draft()
st.set_page_config(page_title=t("ui.title"), page_icon="💃", layout="wide")


def _render_steps(team: Team) -> None:
    """Where the coach stands: one card per step, each linking to its page."""
    st.subheader(t("ui.home.steps"))
    team_step, survey_step, solve_step = st.columns(3)
    with team_step, st.container(border=True):
        st.markdown(
            t(
                "ui.home.step_team",
                n_dancers=len(team.dancers),
                n_positions=team.n_positions,
                n_rules=len(common.rules_of(team)),
            )
        )
        common.page_link("team")
    with survey_step, st.container(border=True):
        answered, total = common.survey_progress(team)
        st.markdown(t("ui.home.step_survey", n=answered, total=total))
        st.progress(answered / total if total else 0.0)
        common.page_link("survey")
    with solve_step, st.container(border=True):
        solved = common.get_result() is not None
        st.markdown(t("ui.home.step_solution_done" if solved else "ui.home.step_solution_open"))
        common.page_link("solution")


def _veto_description(config: SolverConfig) -> str:
    """Which no-gos the pre-check treats as walls, in the coach's words."""
    if config.veto_tier is None:
        return t("ui.solve.veto_none")
    return t("ui.feasibility.veto_upto", label=common.rank_label(config.veto_tier, "not_desired"))


def _render_precheck(team: Team) -> None:
    """Team size and the counting pre-check from SPEC.md 7, read-only.

    The verdict depends on the veto tier and the wish scope, which are set on the Solution
    page -- so it uses the configuration the coach actually chose, and says so, rather than
    quietly assuming a default one (SPEC.md 10).
    """
    st.divider()
    st.subheader(t("ui.feasibility.header"))
    st.markdown(
        t(
            "team.summary",
            n_dancers=len(team.dancers),
            n_leaders=len(team.by_role(Role.LEADER)),
            n_followers=len(team.by_role(Role.FOLLOWER)),
            n_positions=team.n_positions,
            labels=", ".join(team.labels),
        )
    )
    config = common.get_config()
    common.render_feasibility(team, config)
    st.caption(
        t(
            "ui.feasibility.assumes",
            veto=_veto_description(config),
            scope=common.scope_label(config.scope),
        )
    )
    common.page_link("solution")


def render_home() -> None:
    """The start page: three ways in while nothing is loaded, the overview once something is."""
    common.page_header("ui.title", "ui.subtitle")
    if common.draft_was_restored():
        st.info(t("ui.draft.restored"))
    # Editing works everywhere; solving needs a solver. Say which install this is up front,
    # rather than letting the coach find out two pages later (SPEC.md 14).
    if not common.SOLVER_AVAILABLE:
        st.info(t("ui.solver.editor_only"))

    team = common.get_team()
    if team is None:
        st.subheader(t("ui.load.header"))
        st.info(t("ui.home.welcome"))
        common.render_load_controls("home", columns=True)
        return
    _render_steps(team)
    _render_precheck(team)


pages = {
    "home": st.Page(render_home, title=t("nav.home"), icon="🏠", default=True),
    "team": st.Page("pages/team.py", title=t("nav.team"), icon="🧑‍🤝‍🧑"),
    "survey": st.Page("pages/survey.py", title=t("nav.survey"), icon="📝"),
    "solution": st.Page("pages/solution.py", title=t("nav.solution"), icon="🎯"),
}

# The menu is hidden here and drawn by the sidebar helper instead, below the workspace: the
# file the coach is working on comes first, the pages second.
navigation = st.navigation({t("nav.section"): list(pages.values())}, position="hidden")
common.render_sidebar(pages)
# A deep link into the browser build arrives on the default page: the static host answered
# /survey with the shell, and stlite's client does not resolve the path the way Streamlit's
# own server does. Verified in Chrome -- see common.initial_page (SPEC.md 14.7).
requested = common.initial_page(list(pages.values()), navigation)
if requested is not None:
    st.switch_page(requested)
navigation.run()
