"""Draft persistence across a page reload -- browser-side on both targets, nothing on disk.

SPEC.md 9 and 14. The coach's *file* is still written by exactly one thing,
``st.download_button``. What this module keeps is a **draft**: the working team as it stands
right now, so that a reload, a stray back button or a phone locking its screen does not throw
away twenty minutes of survey entry. A draft is not a save, is never presented as one, and
never clears the unsaved-changes warning.

Two backends behind one interface, because a reload means something different on each target:

* **Browser build** (``sys.platform == "emscripten"``): a YAML file inside one of stlite's
  ``idbfsMountpoints`` directories, which is to say the browser's IndexedDB. A reload restarts
  the whole Pyodide worker, so nothing in Python memory could possibly survive it -- but the
  mount does, and nothing ever leaves the device.
* **Server build**: a reload only drops the websocket session, so process memory does survive.
  A random token in ``?draft=`` -- the one part of the page state a refresh preserves by itself
  -- keys an in-RAM store with a TTL. The server's filesystem is never touched; the container
  it runs in is mounted read-only.

Both are best effort. Every entry point swallows its own failures: a draft that cannot be
written must never break the page the coach is standing on. A private window with IndexedDB
disabled simply degrades to "a reload loses the team", which is where this project started.
"""

from __future__ import annotations

import logging
import secrets
import sys
from pathlib import Path
from typing import Final

import streamlit as st

from dancepartner.model import Team
from dancepartner.storage import StorageError, dump_team, parse_team

logger = logging.getLogger(__name__)

IS_WASM: Final = sys.platform == "emscripten"
"""Running inside Pyodide -- the stlite build served from GitHub Pages (SPEC.md 14)."""

DRAFT_PARAM: Final = "draft"
"""Query parameter naming the server-side draft. A refresh keeps the URL; that is the trick."""

_TOKEN_KEY: Final = "draft_token"
"""Where the token lives during a session.

The URL alone is not enough. ``st.navigation`` rewrites the address when the coach opens another
page -- ``/?draft=abc`` becomes ``/team`` -- and drops the query string doing it, so a reload
anywhere but Home would find no token and restore nothing. Session state survives navigation but
not a reload; the URL survives a reload but not navigation. Keeping the token in both, and
re-stamping the URL whenever it has been stripped, is what makes it survive either.
"""

# Must match idbfsMountpoints in the generated index.html. It has to be a single top-level
# directory: stlite mounts with a bare `FS.mkdir(mountpoint)`, which needs the parent to exist
# and the directory itself not to. A nested path like /mnt/dancepartner fails the whole boot
# with an ErrnoError before Streamlit ever renders.
MOUNTPOINT: Final = Path("/mnt")
DRAFT_FILE: Final = MOUNTPOINT / "team.draft.yaml"

_TTL_SECONDS: Final = 12 * 60 * 60
_MAX_DRAFTS: Final = 256


# -- browser backend --------------------------------------------------------------------------
#
# stlite flushes the mount to IndexedDB by itself: its worker runtime patches
# AppSession._on_scriptrunner_event to call FS.syncfs(false) whenever a script run finishes, and
# calls FS.syncfs(true) at boot to read it back. Writing the file is genuinely all we do.


def _wasm_read() -> str | None:
    try:
        return DRAFT_FILE.read_text(encoding="utf-8")
    except OSError:  # never mounted, never written, quota exhausted -- all mean "no draft"
        return None


def _wasm_write(text: str) -> None:
    try:
        MOUNTPOINT.mkdir(parents=True, exist_ok=True)
        DRAFT_FILE.write_text(text, encoding="utf-8")
    except OSError:
        logger.debug("could not write the browser draft", exc_info=True)


def _wasm_clear() -> None:
    try:
        DRAFT_FILE.unlink(missing_ok=True)
    except OSError:
        logger.debug("could not remove the browser draft", exc_info=True)


# -- server backend ---------------------------------------------------------------------------


@st.cache_resource(ttl=_TTL_SECONDS, max_entries=_MAX_DRAFTS, show_spinner=False)
def _slot(token: str) -> dict[str, str]:
    """A mutable one-entry box for one browser's draft, keyed by its token.

    ``st.cache_resource`` gives per-token expiry and LRU eviction for free: once a token has
    not been touched for :data:`_TTL_SECONDS`, Streamlit drops the entry and the draft is gone.
    It is process memory and only process memory -- unlike ``st.cache_data`` there is no
    ``persist=`` to accidentally turn on, which is what lets SPEC.md 14.5 promise that no
    survey data reaches the server's disk.
    """
    return {}


def _token() -> str | None:
    """This browser's draft token: from the session if it has one, otherwise from the URL."""
    remembered = st.session_state.get(_TOKEN_KEY)
    if isinstance(remembered, str) and remembered:
        return remembered
    value = st.query_params.get(DRAFT_PARAM)
    if isinstance(value, str) and value:
        st.session_state[_TOKEN_KEY] = value
        return value
    return None


def stamp_url() -> None:
    """Put the session's token back in the URL if something stripped it.

    Called on every rerun, because ``st.navigation`` drops the query string each time the coach
    changes page. Writing to ``st.query_params`` triggers a rerun, so this only writes when the
    URL actually disagrees -- one extra rerun per navigation, and then it settles.
    """
    token = st.session_state.get(_TOKEN_KEY)
    if isinstance(token, str) and token and st.query_params.get(DRAFT_PARAM) != token:
        st.query_params[DRAFT_PARAM] = token


def _mint() -> str:
    """Give this browser a token, in the session and in the URL.

    Idempotent: it only mints when there is none, so however ``st.query_params`` assignment
    interacts with reruns, the next pass finds one and stops.
    """
    token = _token()
    if token is None:
        token = secrets.token_urlsafe(16)
        st.session_state[_TOKEN_KEY] = token
        st.query_params[DRAFT_PARAM] = token
    return token


# -- the interface ------------------------------------------------------------------------------


def load_draft() -> Team | None:
    """The draft for this browser, or ``None`` if there is none or it cannot be read."""
    if IS_WASM:
        text = _wasm_read()
    else:
        token = _token()
        text = _slot(token).get("yaml") if token else None
    if not text:
        return None
    try:
        return parse_team(text)
    except (StorageError, ValueError):
        # A draft written by an older version of the model is not worth an error page.
        logger.debug("discarding an unreadable draft", exc_info=True)
        return None


def save_draft(team: Team) -> None:
    """Record ``team`` as this browser's draft. Never raises."""
    try:
        text = dump_team(team)
    except (StorageError, ValueError):  # pragma: no cover -- a Team always serialises
        logger.debug("could not serialise the draft", exc_info=True)
        return
    if IS_WASM:
        _wasm_write(text)
    else:
        _slot(_mint())["yaml"] = text


def clear_draft() -> None:
    """Forget this browser's draft, and stop a shared or bookmarked URL from resolving one."""
    if IS_WASM:
        _wasm_clear()
        return
    token = _token()
    if token is not None:
        _slot(token).clear()
        st.session_state.pop(_TOKEN_KEY, None)
        st.query_params.pop(DRAFT_PARAM, None)


def has_draft() -> bool:
    """Whether there is anything for :func:`clear_draft` to remove."""
    if IS_WASM:
        return DRAFT_FILE.exists()
    token = _token()
    return bool(token and _slot(token).get("yaml"))
