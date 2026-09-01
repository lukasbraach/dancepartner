"""Draft persistence: a reload must not cost the coach an evening of survey entry.

SPEC.md 14.4. Two backends, tested the way each actually runs: the browser one against a
temporary directory standing in for the IndexedDB mount, the server one end to end through
Home.py, because minting the token, putting it in the URL and reading it back on the next
visit only means anything inside a real script run.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

import persistence
from dancepartner.i18n import TABLES, Language
from dancepartner.model import Team
from dancepartner.storage import dump_team, load_team

REPO_ROOT = Path(__file__).resolve().parents[1]
HOME = str(REPO_ROOT / "app" / "Home.py")
EXAMPLE = str(REPO_ROOT / "data" / "team.example.yaml")


@pytest.fixture
def wasm(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Run the body as if it were inside Pyodide, with the mount pointed at ``tmp_path``."""
    mount = tmp_path / "mnt"
    monkeypatch.setattr(persistence, "IS_WASM", True)
    monkeypatch.setattr(persistence, "MOUNTPOINT", mount)
    yield mount


@pytest.fixture(autouse=True)
def _fresh_store() -> Iterator[None]:
    """Drop the in-RAM draft store between tests -- st.cache_resource outlives an AppTest."""
    persistence._slot.clear()
    yield
    persistence._slot.clear()


# -- the browser backend ----------------------------------------------------------------------


def test_the_browser_draft_survives_a_reload(wasm: Path, tiny: Team) -> None:
    assert persistence.load_draft() is None
    persistence.save_draft(tiny)
    # A reload restarts the Pyodide worker, so only the mount can carry anything across.
    assert list(wasm.glob("*.draft.yaml"))
    assert dump_team(persistence.load_draft() or tiny) == dump_team(tiny)


def test_a_reload_with_no_token_finds_the_most_recent_draft(wasm: Path, tiny: Team) -> None:
    """A stripped URL must still land the coach back where they were."""
    persistence.save_draft(tiny)
    st.session_state.clear()  # what a reload leaves behind: an empty session, files on the mount
    assert dump_team(persistence.load_draft() or tiny) == dump_team(tiny)


def test_loading_again_keeps_the_previous_version(wasm: Path, tiny: Team, small: Team) -> None:
    """The whole point of minting per load: what was open before is still reachable."""
    persistence.mint_new()
    persistence.save_draft(tiny)
    persistence.mint_new()
    persistence.save_draft(small)

    earlier = persistence.history()
    assert len(earlier) == 1
    assert earlier[0].n_dancers == len(tiny.dancers)
    assert dump_team(persistence.restore(earlier[0].token) or small) == dump_team(tiny)


def test_the_browser_history_is_pruned(wasm: Path, tiny: Team) -> None:
    """IndexedDB has a finite quota and nothing else cleans the mount."""
    for _ in range(persistence.MAX_HISTORY + 4):
        persistence.mint_new()
        persistence.save_draft(tiny)
    assert len(list(wasm.glob("*.draft.yaml"))) == persistence.MAX_HISTORY


def test_the_browser_draft_can_be_discarded(wasm: Path, tiny: Team) -> None:
    persistence.save_draft(tiny)
    persistence.mint_new()
    persistence.save_draft(tiny)
    assert persistence.has_draft()
    persistence.clear_draft()
    # Discarding clears the whole history, not just the version currently open.
    assert not persistence.has_draft()
    assert persistence.load_draft() is None
    assert persistence.history() == []


def test_an_unmounted_browser_filesystem_is_not_an_error(
    tiny: Team, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A private window with IndexedDB off degrades to "a reload loses the team", not a crash."""
    monkeypatch.setattr(persistence, "IS_WASM", True)
    monkeypatch.setattr(persistence, "MOUNTPOINT", Path("/proc/nonexistent/dancepartner"))
    persistence.save_draft(tiny)  # must not raise
    assert persistence.load_draft() is None
    assert not persistence.has_draft()
    persistence.clear_draft()  # must not raise either


def test_an_unreadable_draft_is_discarded_not_raised(wasm: Path) -> None:
    wasm.mkdir(parents=True, exist_ok=True)
    (wasm / "broken.draft.yaml").write_text("this: [is, not, a, team", encoding="utf-8")
    assert persistence.load_draft() is None
    # It still shows up in the history, counted as empty rather than crashing the page.
    assert [e.n_dancers for e in persistence.history()] == [0]


# -- the server backend, through the app ---------------------------------------------------------


def test_loading_a_team_mints_a_draft_token() -> None:
    at = AppTest.from_file(HOME, default_timeout=60).run()
    assert persistence.DRAFT_PARAM not in at.query_params
    _click(at, "ui.load.example_button")
    assert not at.exception
    assert _token(at)


def test_a_refresh_restores_the_team_from_its_token() -> None:
    first = AppTest.from_file(HOME, default_timeout=60).run()
    _click(first, "ui.load.example_button")
    token = _token(first)

    # A refresh is a brand new session that keeps only the URL.
    second = AppTest.from_file(HOME, default_timeout=60)
    second.query_params[persistence.DRAFT_PARAM] = token
    second.run()

    assert not second.exception
    restored = second.session_state["team"]
    assert dump_team(restored) == dump_team(load_team(Path(EXAMPLE)))
    # A draft is not the file on disk, so the warning has to stay up.
    assert second.session_state["dirty"] is True
    assert TABLES[Language.EN]["ui.draft.restored"] in _texts(second)


def test_an_unknown_token_restores_nothing() -> None:
    at = AppTest.from_file(HOME, default_timeout=60)
    at.query_params[persistence.DRAFT_PARAM] = "not-a-real-token"
    at.run()
    assert not at.exception
    assert "team" not in at.session_state


def test_a_seeded_session_is_left_alone(tiny: Team) -> None:
    """restore_draft must never overwrite a team something else already put in the session."""
    first = AppTest.from_file(HOME, default_timeout=60).run()
    _click(first, "ui.load.example_button")
    token = _token(first)

    second = AppTest.from_file(HOME, default_timeout=60)
    second.query_params[persistence.DRAFT_PARAM] = token
    second.session_state["team"] = tiny
    second.session_state["dirty"] = False
    second.run()

    assert dump_team(second.session_state["team"]) == dump_team(tiny)
    assert second.session_state["dirty"] is False


def test_the_token_is_restamped_after_navigation_strips_it() -> None:
    """st.navigation rewrites the URL on every page change and drops the query string with it.

    Found by driving a real browser, not by AppTest, which does not model that rewrite: opening
    Team turned ``/?draft=abc`` into ``/team``, and a reload from there restored nothing. The
    session keeps the token; ``stamp_url`` is what puts it back (SPEC.md 14.4).
    """
    at = AppTest.from_file(HOME, default_timeout=60).run()
    _click(at, "ui.load.example_button")
    token = _token(at)

    # Exactly what navigating to another page does to the address bar.
    del at.query_params[persistence.DRAFT_PARAM]
    at.run()

    assert not at.exception
    assert _token(at) == token


def test_loading_twice_offers_the_first_team_back() -> None:
    """The server side of minting per load, driven through the page.

    Browser-back would be the natural control and is not available (streamlit#13963), so the
    history is offered in the page instead -- this is what backs that list.
    """
    at = AppTest.from_file(HOME, default_timeout=60).run()
    _click(at, "ui.load.example_button")
    first_token = _token(at)
    example_size = len(at.session_state["team"].dancers)

    _click(at, "ui.load.create_button")
    assert _token(at) != first_token, "a second load must start a new version"
    assert len(at.session_state["team"].dancers) == 2

    # history() reads session state, and the test process has its own bare session -- so ask
    # the app, not the module.
    assert len(at.session_state[persistence._HISTORY_KEY]) == 2

    # The history is offered as a restore control per earlier version.
    restore = TABLES[Language.EN]["ui.draft.restore"]
    assert [b for b in at.button if b.label == restore], "no way back to the earlier version"
    assert str(example_size) in _texts(at), "the earlier version should be listed by size"


def test_restoring_an_earlier_version_brings_the_team_back() -> None:
    """The rollback the back button cannot give us (streamlit#13963), as an explicit control."""
    at = AppTest.from_file(HOME, default_timeout=60).run()
    _click(at, "ui.load.example_button")
    example = dump_team(at.session_state["team"])

    _click(at, "ui.load.create_button")
    assert dump_team(at.session_state["team"]) != example

    _click(at, "ui.draft.restore")
    assert not at.exception
    assert dump_team(at.session_state["team"]) == example
    # A restored version is not the file on disk, so the warning has to stay up.
    assert at.session_state["dirty"] is True


def test_editing_does_not_start_a_new_version(tiny: Team) -> None:
    """Only loads mint. Otherwise every keystroke on the survey page adds a history entry."""
    at = AppTest.from_file(HOME, default_timeout=60).run()
    _click(at, "ui.load.example_button")
    token = _token(at)
    before = list(at.session_state[persistence._HISTORY_KEY])

    at.session_state["team"] = tiny
    at.run()
    assert _token(at) == token
    assert at.session_state[persistence._HISTORY_KEY] == before


def test_discarding_the_draft_clears_the_token() -> None:
    at = AppTest.from_file(HOME, default_timeout=60).run()
    _click(at, "ui.load.example_button")
    assert persistence.DRAFT_PARAM in at.query_params

    _click(at, "ui.draft.discard")
    assert not at.exception
    assert persistence.DRAFT_PARAM not in at.query_params


def _click(at: AppTest, key: str) -> AppTest:
    """Click the button carrying the i18n string ``key``.

    By label rather than by index: Home's button order has changed before, and an index makes
    the test fail somewhere unrelated to the change that broke it (SPEC.md 12).
    """
    label = TABLES[Language.EN][key]
    return next(b for b in at.button if b.label == label).click().run()


def _param(at: AppTest, name: str) -> str:
    """One query parameter as AppTest reports it.

    AppTest mirrors the raw query dict, so values arrive as one-element lists rather than the
    plain strings ``st.query_params`` hands the running script.
    """
    raw = at.query_params[name]
    return raw[0] if isinstance(raw, list) else str(raw)


def _token(at: AppTest) -> str:
    """The draft token as AppTest reports it."""
    return _param(at, persistence.DRAFT_PARAM)


def _texts(at: AppTest) -> str:
    """Every string the page rendered, joined -- mirrors the helper in test_app.py."""
    parts = [
        element.value
        for group in (at.markdown, at.caption, at.info, at.success, at.error, at.warning)
        for element in group
    ]
    return "\n".join(str(p) for p in parts)


# -- the language preference --------------------------------------------------------------------


def test_the_browser_remembers_the_language_across_a_reload(wasm: Path) -> None:
    """Web Workers have no localStorage at all, so the preference rides the draft mount.

    Which is the same IndexedDB the drafts already live in, and survives the same reload.
    """
    assert persistence.load_language() is None
    persistence.save_language("de")
    st.session_state.clear()  # what a reload leaves behind
    assert persistence.load_language() == "de"


def test_the_language_store_is_browser_only() -> None:
    """The server build must not keep one coach's choice where the next coach's session sees it."""
    persistence.save_language("de")
    assert persistence.load_language() is None


def test_an_unwritable_mount_is_not_an_error(wasm: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Best effort, like every other entry point here: a preference is never worth an error page."""
    monkeypatch.setattr(persistence, "MOUNTPOINT", wasm / "file")
    (wasm).mkdir(parents=True, exist_ok=True)
    (wasm / "file").write_text("not a directory", encoding="utf-8")
    persistence.save_language("de")
    assert persistence.load_language() is None


def test_the_language_is_stamped_into_the_url_beside_the_draft() -> None:
    """The static shell reads it from there -- it renders before Python exists (SPEC.md 14)."""
    at = AppTest.from_file(HOME, default_timeout=60).run()
    assert _param(at, persistence.LANG_PARAM) == Language.EN.value

    at.session_state["language"] = Language.DE.value
    at.run()
    assert _param(at, persistence.LANG_PARAM) == Language.DE.value
    assert TABLES[Language.DE]["ui.title"] in [element.value for element in at.title]
