"""Streamlit entry point: declares the navigation and renders the start page.

Run with ``streamlit run app/Home.py`` from the repository root.

SPEC.md 5 lists the pages as ``1_Team.py`` / ``2_Umfrage.py`` / ``3_Loesung.py`` /
``4_Analyse.py``. Two deliberate departures, agreed before implementation:

* The module names are English, per the language policy in SPEC.md 2. Streamlit derives a
  file-based page's sidebar label from its filename, which would put untranslated
  identifiers in front of the coach. Going through ``st.navigation`` puts the label in
  ``i18n.py`` where every other user-facing string lives.
* The numeric prefixes are gone. They only ever encoded sidebar order, which the page list
  below now fixes explicitly, and ``1_Team`` is not a valid module name for ``mypy --strict``.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

import common
from dancepartner.feasibility import check_feasibility
from dancepartner.i18n import Language, t
from dancepartner.model import DEFAULT_N_POSITIONS, Role
from dancepartner.storage import MalformedYamlError, StorageError, parse_team, save_team

common.sync_language()
st.set_page_config(page_title=t("ui.title"), page_icon="💃", layout="wide")


def _load_from_path(raw: str) -> None:
    """Load a team from a path typed by the coach, reporting failures through i18n."""
    path = Path(raw).expanduser()
    try:
        team = parse_team(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        st.error(t("error.file_not_found", path=path))
    except MalformedYamlError as exc:
        st.error(t("error.invalid_yaml", detail=exc))
    except StorageError as exc:
        st.error(t("error.invalid_shape", detail=exc))
    except ValueError as exc:  # pydantic ValidationError -- a SPEC.md 6 rule broke.
        st.error(t("error.invalid_team", detail=exc))
    else:
        # Freshly loaded means it matches the file: not dirty.
        common.set_team(team, path=path, dirty=False)
        st.success(t("ui.load.loaded", path=path))


def _load_uploaded(data: bytes, name: str) -> None:
    """Load a team from an uploaded file, reporting failures through i18n."""
    try:
        team = parse_team(data.decode("utf-8"))
    except MalformedYamlError as exc:
        st.error(t("error.invalid_yaml", detail=exc))
    except StorageError as exc:
        st.error(t("error.invalid_shape", detail=exc))
    except ValueError as exc:
        st.error(t("error.invalid_team", detail=exc))
    else:
        # An upload has no path on this machine, so it starts dirty: there is nothing to
        # overwrite until the coach names a target.
        common.set_team(team, dirty=True)
        st.success(t("ui.load.loaded", path=name))


def _render_load() -> None:
    """The three ways in: an upload, a fresh team, or the bundled example."""
    st.subheader(t("ui.load.header"))
    from_upload, from_example = st.columns(2)

    with from_upload:
        st.markdown(f"**{t('ui.load.upload')}**")
        upload = st.file_uploader(t("ui.load.uploader"), type=["yaml", "yml"])
        if upload is not None:
            _load_uploaded(upload.getvalue(), upload.name)

        st.markdown(f"**{t('ui.load.create')}**")
        n_positions = st.number_input(
            t("ui.load.n_positions"), min_value=1, max_value=26, value=DEFAULT_N_POSITIONS
        )
        if st.button(t("ui.load.create_button"), use_container_width=True):
            common.set_team(common.empty_team(int(n_positions)))

    with from_example:
        st.markdown(f"**{t('ui.load.example')}**")
        st.caption(t("ui.load.example_hint"))
        if st.button(t("ui.load.example_button"), use_container_width=True):
            _load_from_path(str(common.EXAMPLE_TEAM))


def _render_summary() -> None:
    """Team size, survey response rate, and the counting pre-check from SPEC.md 7."""
    team = common.get_team()
    if team is None:
        return

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
    st.markdown(t("team.surveys", n_surveys=len(team.surveys), n_dancers=len(team.dancers)))

    # The pre-check depends on veto_tier and scope, so it must see the configuration the coach
    # actually chose rather than a default one.
    issues = check_feasibility(team, common.get_config())
    if issues:
        st.markdown(t("check.issues", count=len(issues)))
        common.show_issues(list(issues))
    else:
        st.success(t("check.ok"))
    st.caption(t("check.caveat"))


def _render_save() -> None:
    """Explicit save. Never automatic -- see the note in common.py."""
    team = common.get_team()
    if team is None:
        return

    st.divider()
    st.subheader(t("ui.save.header"))
    st.caption(t("ui.save.comment_warning"))
    target = st.text_input(t("ui.save.path"), value=common.team_path())
    if st.button(t("ui.save.button"), type="primary", disabled=not target.strip()):
        path = Path(target.strip()).expanduser()
        try:
            save_team(team, path)
        except OSError as exc:
            st.error(t("error.invalid_shape", detail=exc))
        else:
            common.mark_saved(path)
            st.success(t("ui.saved_at", path=path))


def render_home() -> None:
    """The start page: load or create a team, see the pre-check, save explicitly."""
    common.page_header("ui.title", "ui.subtitle")
    _render_load()
    _render_summary()
    _render_save()


st.sidebar.selectbox(
    t("ui.language"),
    options=[language.value for language in Language],
    format_func=lambda code: t(f"language.{code}"),
    key=common.LANGUAGE_KEY,
)

pages = [
    st.Page(render_home, title=t("nav.home"), icon="🏠", default=True),
    st.Page("pages/team.py", title=t("nav.team"), icon="🧑‍🤝‍🧑"),
    st.Page("pages/survey.py", title=t("nav.survey"), icon="📝"),
    st.Page("pages/solution.py", title=t("nav.solution"), icon="🎯"),
    st.Page("pages/analysis.py", title=t("nav.analysis"), icon="📊"),
]

st.navigation({t("nav.section"): pages}).run()
