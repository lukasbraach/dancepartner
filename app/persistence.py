"""Draft persistence and version history -- browser-side on both targets, nothing on disk.

SPEC.md 9 and 14.4. The coach's *file* is still written by exactly one thing,
``st.download_button``. What this module keeps is a **draft**: the working team as it stands
right now, so that a reload, a stray back button or a phone locking its screen does not throw
away twenty minutes of survey entry. A draft is not a save, is never presented as one, and
never clears the unsaved-changes warning.

Each *load* -- an upload, the example, a fresh team -- mints a new token and leaves the previous
draft where it was, so loading something else does not destroy what you had. Edits overwrite the
current token. That gives a short version history, offered on Home.

Two backends behind one interface, because a reload means something different on each target:

* **Browser build** (``sys.platform == "emscripten"``): one YAML file per token inside an stlite
  ``idbfsMountpoints`` directory, which is to say the browser's IndexedDB. A reload restarts the
  whole Pyodide worker, so nothing in Python memory could survive it -- but the mount does, and
  with it the whole history. Nothing ever leaves the device.
* **Server build**: a reload only drops the websocket session, so process memory does survive.
  A random token in ``?draft=`` -- the one part of the page state a refresh preserves by itself
  -- keys an in-RAM store with a TTL. The server's filesystem is never touched; the container it
  runs in is mounted read-only. The *history* lives in session state, so a reload keeps the
  current draft but not the older ones; the browser build keeps both.

Why the history is offered in the page rather than through the browser's back button, which is
what one would reach for first: streamlit#13963. In a ``st.navigation`` app a back press changes
the URL and reruns the script, but ``st.query_params`` still reports the *newest* value, so
Python cannot see which draft the URL points at. ``st.context.url`` is no way out either -- it
carries no query string at all. Verified on 1.62; the browser build's 1.57 is older still.

Both backends are best effort. Every entry point swallows its own failures: a draft that cannot
be written must never break the page the coach is standing on. A private window with IndexedDB
disabled simply degrades to "a reload loses the team", which is where this project started.
"""

from __future__ import annotations

import logging
import secrets
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import streamlit as st

from dancepartner.model import Team
from dancepartner.storage import StorageError, dump_team, parse_team

logger = logging.getLogger(__name__)

IS_WASM: Final = sys.platform == "emscripten"
"""Running inside Pyodide -- the stlite build served from GitHub Pages (SPEC.md 14)."""

DRAFT_PARAM: Final = "draft"
"""Query parameter naming the current draft. A refresh keeps the URL; that is the trick."""

LANG_PARAM: Final = "lang"
"""Query parameter carrying the chosen language, stamped the same way the draft token is.

It is what makes the choice survive a reload on *both* targets, and it is also the only way
the static shell can know which language to write its loading screen in -- that runs before
Python exists, so the URL is the one channel open to it (SPEC.md 14.8).
"""

_TOKEN_KEY: Final = "draft_token"
"""Where the token lives during a session.

The URL alone is not enough. ``st.navigation`` rewrites the address when the coach opens another
page -- ``/?draft=abc`` becomes ``/team`` -- and drops the query string doing it, so a reload
anywhere but Home would find no token and restore nothing. Session state survives navigation but
not a reload; the URL survives a reload but not navigation. Keeping the token in both, and
re-stamping the URL whenever it has been stripped, is what makes it survive either.
"""

_HISTORY_KEY: Final = "draft_history"
"""Tokens this session has minted, oldest first. The browser build reads the mount instead."""

# Must match idbfsMountpoints in the generated index.html. It has to be a single top-level
# directory: stlite mounts with a bare `FS.mkdir(mountpoint)`, which needs the parent to exist
# and the directory itself not to. A nested path like /mnt/dancepartner fails the whole boot
# with an ErrnoError before Streamlit ever renders.
MOUNTPOINT: Final = Path("/mnt")
_SUFFIX: Final = ".draft.yaml"
_LANGUAGE_FILE: Final = "language"

MAX_HISTORY: Final = 10
"""Drafts kept per browser. IndexedDB has a finite quota and nothing else prunes the mount."""

_TTL_SECONDS: Final = 12 * 60 * 60
_MAX_DRAFTS: Final = 2048
"""Server-side LRU budget, shared across every browser -- so it has to cover history, not just
one draft per coach."""


@dataclass(frozen=True)
class DraftEntry:
    """One stored version, for the history list on Home."""

    token: str
    saved_at: float
    n_dancers: int


# -- browser backend --------------------------------------------------------------------------
#
# stlite flushes the mount to IndexedDB by itself: its worker runtime patches
# AppSession._on_scriptrunner_event to call FS.syncfs(false) whenever a script run finishes, and
# calls FS.syncfs(true) at boot to read it back. Writing the file is genuinely all we do.


def _path(token: str) -> Path:
    return MOUNTPOINT / f"{token}{_SUFFIX}"


def _wasm_read(token: str) -> str | None:
    try:
        return _path(token).read_text(encoding="utf-8")
    except OSError:  # never mounted, never written, quota exhausted -- all mean "no draft"
        return None


def _wasm_write(token: str, text: str) -> None:
    try:
        MOUNTPOINT.mkdir(parents=True, exist_ok=True)
        _path(token).write_text(text, encoding="utf-8")
    except OSError:
        logger.debug("could not write the browser draft", exc_info=True)
        return
    _wasm_prune()


def _wasm_files() -> list[Path]:
    """Every stored draft, newest first."""
    try:
        found = [p for p in MOUNTPOINT.glob(f"*{_SUFFIX}") if p.is_file()]
    except OSError:
        return []
    return sorted(found, key=lambda p: p.stat().st_mtime, reverse=True)


def _wasm_prune() -> None:
    """Drop everything past :data:`MAX_HISTORY`, oldest first."""
    for stale in _wasm_files()[MAX_HISTORY:]:
        try:
            stale.unlink(missing_ok=True)
        except OSError:  # pragma: no cover -- unlink on a listed file
            logger.debug("could not prune a browser draft", exc_info=True)


# -- the language preference --------------------------------------------------------------------
#
# The mount, not localStorage. Python runs in a Web Worker here and Web Workers have no
# localStorage at all -- it is a synchronous main-thread-only API. IndexedDB is what a worker
# does get, and the draft mount is already IndexedDB and already flushed after every script
# run, so the preference rides along with it for free.
#
# There is no server-side counterpart: process memory would leak one coach's choice into the
# next coach's session, and the container's filesystem is read-only by design (SPEC.md 14.8).
# The server build persists through LANG_PARAM instead, which covers a reload if not a brand
# new visit.


def load_language() -> str | None:
    """The language code stored in this browser, or ``None``. Never raises."""
    if not IS_WASM:
        return None
    try:
        code = (MOUNTPOINT / _LANGUAGE_FILE).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return code or None


def save_language(code: str) -> None:
    """Remember ``code`` for the next visit to this browser. Never raises."""
    if not IS_WASM:
        return
    try:
        MOUNTPOINT.mkdir(parents=True, exist_ok=True)
        (MOUNTPOINT / _LANGUAGE_FILE).write_text(code, encoding="utf-8")
    except OSError:
        logger.debug("could not store the language preference", exc_info=True)


# -- server backend ---------------------------------------------------------------------------


@st.cache_resource(ttl=_TTL_SECONDS, max_entries=_MAX_DRAFTS, show_spinner=False)
def _slot(token: str) -> dict[str, str]:
    """A mutable one-entry box for one draft, keyed by its token.

    ``st.cache_resource`` gives per-token expiry and LRU eviction for free: once a token has not
    been touched for :data:`_TTL_SECONDS`, Streamlit drops the entry and the draft is gone. It is
    process memory and only process memory -- unlike ``st.cache_data`` there is no ``persist=``
    to turn on by accident, which is what lets SPEC.md 14.5 promise that no survey data reaches
    the server's disk.
    """
    return {}


def _session_history() -> list[str]:
    history = st.session_state.get(_HISTORY_KEY)
    return list(history) if isinstance(history, list) else []


# -- tokens -------------------------------------------------------------------------------------


def _token() -> str | None:
    """This browser's current draft token: from the session if it has one, else from the URL."""
    remembered = st.session_state.get(_TOKEN_KEY)
    if isinstance(remembered, str) and remembered:
        return remembered
    value = st.query_params.get(DRAFT_PARAM)
    if isinstance(value, str) and value:
        _adopt(value)
        return value
    return None


def _adopt(token: str) -> None:
    """Make ``token`` current, recording it in this session's history."""
    st.session_state[_TOKEN_KEY] = token
    history = [t for t in _session_history() if t != token]
    history.append(token)
    st.session_state[_HISTORY_KEY] = history[-MAX_HISTORY:]


def stamp_url(language: str | None = None) -> None:
    """Put the session's token -- and its language -- back in the URL if something stripped it.

    Called on every rerun, because ``st.navigation`` drops the query string each time the coach
    changes page. Writing to ``st.query_params`` triggers a rerun, so this only writes when the
    URL actually disagrees -- one extra rerun per navigation, and then it settles.
    """
    token = st.session_state.get(_TOKEN_KEY)
    if isinstance(token, str) and token and st.query_params.get(DRAFT_PARAM) != token:
        st.query_params[DRAFT_PARAM] = token
    if language and st.query_params.get(LANG_PARAM) != language:
        st.query_params[LANG_PARAM] = language


def _mint() -> str:
    """The current token, creating one if this browser has none yet."""
    token = _token()
    if token is None:
        token = mint_new()
    return token


def mint_new() -> str:
    """Start a new version: a fresh token, leaving the previous draft untouched.

    Called by the *load* paths only. Editing overwrites the current version; loading something
    else begins another one, so the team you had is still there to go back to.
    """
    token = secrets.token_urlsafe(16)
    _adopt(token)
    st.query_params[DRAFT_PARAM] = token
    return token


# -- the interface ------------------------------------------------------------------------------


def load_draft(token: str | None = None) -> Team | None:
    """A stored draft, defaulting to the current one. ``None`` if there is none or it is broken.

    On the browser build a missing token falls back to the most recently written draft: a plain
    reload with a stripped URL should still come back to where the coach was.
    """
    if token is None:
        token = _token()
    if IS_WASM:
        if token is None:
            recent = _wasm_files()
            text = recent[0].read_text(encoding="utf-8") if recent else None
        else:
            text = _wasm_read(token)
    else:
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
    """Record ``team`` as the current version. Never raises."""
    try:
        text = dump_team(team)
    except (StorageError, ValueError):  # pragma: no cover -- a Team always serialises
        logger.debug("could not serialise the draft", exc_info=True)
        return
    token = _mint()
    if IS_WASM:
        _wasm_write(token, text)
    else:
        _slot(token).update(yaml=text, saved_at=str(time.time()))


def history() -> list[DraftEntry]:
    """Earlier versions, newest first, excluding the one currently loaded.

    The browser build reads the mount, so its history outlives a reload. The server build reads
    session state, so a reload keeps the current draft (through the URL) but not the older ones.
    """
    current = _token()
    entries: list[DraftEntry] = []
    if IS_WASM:
        for path in _wasm_files():
            token = path.name.removesuffix(_SUFFIX)
            if token != current:
                entries.append(_entry(token, path.stat().st_mtime, path.read_text("utf-8")))
    else:
        for token in reversed(_session_history()):
            stored = _slot(token)
            if token != current and stored.get("yaml"):
                entries.append(_entry(token, float(stored.get("saved_at", "0")), stored["yaml"]))
    return entries[:MAX_HISTORY]


def _entry(token: str, saved_at: float, text: str) -> DraftEntry:
    """Describe one stored draft without trusting it to parse."""
    try:
        n_dancers = len(parse_team(text).dancers)
    except (StorageError, ValueError):
        n_dancers = 0
    return DraftEntry(token=token, saved_at=saved_at, n_dancers=n_dancers)


def restore(token: str) -> Team | None:
    """Make ``token`` the current version and return its team, or ``None`` if it is gone."""
    team = load_draft(token)
    if team is not None:
        _adopt(token)
        st.query_params[DRAFT_PARAM] = token
    return team


def clear_draft() -> None:
    """Forget every draft this browser holds, and stop a shared URL from resolving one."""
    if IS_WASM:
        for path in _wasm_files():
            try:
                path.unlink(missing_ok=True)
            except OSError:
                logger.debug("could not remove a browser draft", exc_info=True)
    else:
        for token in _session_history():
            _slot(token).clear()
    st.session_state.pop(_TOKEN_KEY, None)
    st.session_state.pop(_HISTORY_KEY, None)
    st.query_params.pop(DRAFT_PARAM, None)


def has_draft() -> bool:
    """Whether there is anything for :func:`clear_draft` to remove."""
    if IS_WASM:
        return bool(_wasm_files())
    token = _token()
    return bool(token and _slot(token).get("yaml")) or bool(history())
