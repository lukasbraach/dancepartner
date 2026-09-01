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

from datetime import datetime
from typing import Final

import streamlit as st

import common
import persistence
from dancepartner.feasibility import check_feasibility
from dancepartner.i18n import Language, t
from dancepartner.model import DEFAULT_N_POSITIONS, Role
from dancepartner.storage import MalformedYamlError, StorageError, dump_team, parse_team

common.sync_language()
# st.navigation runs this file on every rerun whichever page is showing, so this one call
# covers all five pages (SPEC.md 14.4). It is a no-op once a team is loaded.
common.restore_draft()
st.set_page_config(page_title=t("ui.title"), page_icon="💃", layout="wide")


def _load_example() -> None:
    """Load the bundled example team, reporting failures through i18n."""
    path = common.EXAMPLE_TEAM
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
        # Freshly loaded means it matches the file: not dirty. A load starts a new version,
        # so whatever was open before stays in the history (SPEC.md 14.4).
        common.set_team(team, dirty=False, new_draft=True)


# The file_id already loaded, so the uploader acts once per file rather than once per rerun.
# A comment, not a docstring: Streamlit's magic renders a bare string at module level of the
# entry script straight into the page.
_LAST_UPLOAD: Final = "last_upload_id"


def _load_uploaded(data: bytes) -> None:
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
        # An upload matches the file the coach just picked, so it starts clean; the download
        # button is the only way back out (there is no path on this machine to overwrite). A
        # load starts a new version, so what was open before stays in the history (SPEC.md 14.4).
        common.set_team(team, dirty=False, new_draft=True)


def _render_load() -> None:
    """The three ways in: an upload, a fresh team, or the bundled example."""
    st.subheader(t("ui.load.header"))
    from_upload, from_example = st.columns(2)

    with from_upload:
        st.markdown(f"**{t('ui.load.upload')}**")
        upload = st.file_uploader(t("ui.load.uploader"), type=["yaml", "yml"])
        # `upload is not None` stays true for as long as the file sits in the widget, so this
        # branch re-fires on every rerun. Acting on it unguarded would mint a fresh version --
        # and re-clobber the coach's edits with the file -- once per rerun.
        if upload is not None and st.session_state.get(_LAST_UPLOAD) != upload.file_id:
            st.session_state[_LAST_UPLOAD] = upload.file_id
            _load_uploaded(upload.getvalue())

        st.markdown(f"**{t('ui.load.create')}**")
        n_positions = st.number_input(
            t("ui.load.n_positions"), min_value=1, max_value=26, value=DEFAULT_N_POSITIONS
        )
        if st.button(t("ui.load.create_button"), use_container_width=True):
            common.set_team(common.empty_team(int(n_positions)), new_draft=True)

    with from_example:
        st.markdown(f"**{t('ui.load.example')}**")
        st.caption(t("ui.load.example_hint"))
        if st.button(t("ui.load.example_button"), use_container_width=True):
            _load_example()


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
    """Explicit save, as a download. Never automatic -- see the note in common.py.

    The app has no writable path of its own once it is served to a browser, and the load side
    offers only an upload or the example, so a download is the honest counterpart. Pressing it
    is what clears the unsaved-changes warning.
    """
    team = common.get_team()
    if team is None:
        return

    st.divider()
    st.subheader(t("ui.save.header"))
    st.caption(t("ui.save.comment_warning"))
    if st.download_button(
        t("ui.save.download"),
        data=dump_team(team),
        file_name=common.DOWNLOAD_NAME,
        mime="application/yaml",
        type="primary",
    ):
        common.mark_saved()

    # The draft is the reason a reload is survivable; the download is still the only export.
    st.caption(t("ui.draft.hint"))
    _render_history()
    if persistence.has_draft() and st.button(t("ui.draft.discard")):
        persistence.clear_draft()
        st.success(t("ui.draft.discarded"))


def _render_history() -> None:
    """Earlier versions, and a way back to one.

    The browser's back button would be the obvious control here and is not available: in a
    ``st.navigation`` app a back press leaves ``st.query_params`` reporting the newest value
    (streamlit#13963), so the app cannot tell which version the URL points at. An explicit list
    does not depend on that, and it works the same on both targets -- see app/persistence.py.
    """
    entries = persistence.history()
    if not entries:
        return
    with st.expander(t("ui.draft.history")):
        st.caption(t("ui.draft.history_hint"))
        for entry in entries:
            label, button = st.columns([3, 1])
            when = datetime.fromtimestamp(entry.saved_at).strftime("%H:%M")
            label.write(t("ui.draft.entry", n=entry.n_dancers, when=when))
            if button.button(t("ui.draft.restore"), key=f"restore_{entry.token}"):
                if common.restore_version(entry.token):
                    st.success(t("ui.draft.restored_version"))
                    st.rerun()
                else:
                    st.warning(t("ui.draft.gone"))


def render_home() -> None:
    """The start page: load or create a team, see the pre-check, save explicitly."""
    common.page_header("ui.title", "ui.subtitle")
    if common.draft_was_restored():
        st.info(t("ui.draft.restored"))
    # Editing works everywhere; solving does not. Say which build this is up front, rather
    # than letting the coach find out two pages later (SPEC.md 14).
    if not common.SOLVER_AVAILABLE:
        st.info(t("ui.solver.editor_only"))
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
