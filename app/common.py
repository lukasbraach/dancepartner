"""Shared state and formatting for the Streamlit pages.

The pages are thin: they arrange widgets and call into this module, which in turn calls the
core. Nothing here re-derives a number the core already computes -- see
:mod:`dancepartner.reporting` for the derivations both the CLI and this UI share.

The dependency runs one way only. ``dancepartner`` never imports ``streamlit``; deleting
``app/`` leaves the CLI working (SPEC.md 5).
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING, Final

import streamlit as st
from streamlit.navigation.page import StreamlitPage

import persistence
from dancepartner.i18n import Language, get_language, set_language, t
from dancepartner.model import (
    DEFAULT_N_POSITIONS,
    Dancer,
    Direction,
    Objective,
    PreferenceScope,
    Role,
    ScoreAggregation,
    SolverConfig,
    Survey,
    Team,
    Tier,
)
from dancepartner.scoring import DancerSatisfaction, Solution
from dancepartner.solver import available_backends
from dancepartner.storage import dump_team

if TYPE_CHECKING:  # Importing the solver for real would pull in ortools -- see SOLVER_AVAILABLE.
    from dancepartner.solver import SolveResult

SOLVER_AVAILABLE: Final = bool(available_backends())
"""Whether an assignment can be computed here.

Asked of the dispatcher rather than of one package: there are two backends and the browser
build has only the second of them (SPEC.md 8.1). ``available_backends`` probes with
``find_spec``, so asking costs nothing and never drags a solver in.

It is normally true everywhere, including in the browser. It goes false only where neither
ortools nor highspy is installed -- a CLI-only install of the core, say -- and then the two
solving pages say so instead of failing.
"""

REPO_ROOT: Final = Path(__file__).resolve().parents[1]
EXAMPLE_TEAM: Final = REPO_ROOT / "data" / "team.example.yaml"
DOWNLOAD_NAME: Final = "team.yaml"
"""File name offered by the save download. Not a path the app writes to -- see Home.py."""

# -- session state ------------------------------------------------------------------------
#
# SPEC.md 10: the team lives in st.session_state and reaches disk only when the coach presses
# save. PyYAML cannot preserve comments, so an autosave would quietly strip the documentation
# out of any hand-written team file.

_TEAM: Final = "team"
_DIRTY: Final = "dirty"
_RESULT: Final = "result"
_CONFIG: Final = "config"
LANGUAGE_KEY: Final = "language"
_LANGUAGE_CODES: Final = frozenset(language.value for language in Language)
_RESTORED: Final = "draft_restored"
_RESTORED_NOTICE: Final = "draft_restored_notice"
_ROUTED: Final = "routed_from_url"


_LANGUAGE_STORED: Final = "language_stored"


def _resolve_language() -> str:
    """Where a fresh session gets its language from, most specific source first.

    ``?lang=`` beats the store because it is the more deliberate act -- a shared or bookmarked
    link -- and it is also what a reload preserves on the server build, which has no store.
    Anything unrecognised is ignored rather than raising: a hand-edited URL should not be able
    to break the page.
    """
    for candidate in (st.query_params.get(persistence.LANG_PARAM), persistence.load_language()):
        if isinstance(candidate, str) and candidate in _LANGUAGE_CODES:
            return candidate
    return get_language().value


def sync_language() -> None:
    """Point the core i18n layer at the language chosen in this session, and remember it.

    The core language is a process-wide setting while the choice lives per browser session,
    so Home.py calls this at the top of every rerun, before anything renders a label. A fresh
    session resolves one through :func:`_resolve_language`, falling back to the
    environment-variable default (English when unset).

    The write-back is guarded on having actually changed. It reaches IndexedDB on the browser
    build, and doing that once per rerun for a value that never moves would be pure waste.
    """
    raw = st.session_state.get(LANGUAGE_KEY)
    if not isinstance(raw, str) or raw not in _LANGUAGE_CODES:
        raw = _resolve_language()
        st.session_state[LANGUAGE_KEY] = raw
    set_language(Language(raw))
    if st.session_state.get(_LANGUAGE_STORED) != raw:
        st.session_state[_LANGUAGE_STORED] = raw
        persistence.save_language(raw)


PAGE_PARAM: Final = "page"
"""Query parameter naming the page a deep link asked for. Must match ``wasm/build_static.py``.

Only the browser build ever sets it. A static host has no file behind ``/survey``, so the shell
is served for that path instead -- a ``404.html`` copy on Pages, the service worker on a return
visit, ``wasm/serve.py`` locally -- and the app boots on its default page while the address bar
still says ``/survey``. Streamlit's own server resolves the path for itself, so under
``make ui`` this parameter never appears and :func:`initial_page` finds nothing to do.

The shell has to be the one to translate the path, because Python cannot see it: under stlite
``st.context.url`` is the bare origin, no path and no query string. Verified in Chrome; the
query string is the only channel from the address bar into the script (SPEC.md 14.7).
"""


def initial_page(pages: list[StreamlitPage], selected: StreamlitPage) -> StreamlitPage | None:
    """The page a deep link asked for, when Streamlit has not already opened it.

    Consumed once per session and cleared out of the URL either way, so client-side navigation
    afterwards is left entirely alone.

    Returns:
        The page to switch to, or ``None`` if the URL agrees already or names nothing known.
    """
    if st.session_state.get(_ROUTED):
        return None
    st.session_state[_ROUTED] = True
    wanted = st.query_params.get(PAGE_PARAM)
    if wanted is None:
        return None
    st.query_params.pop(PAGE_PARAM, None)
    if wanted == selected.url_path:
        return None
    return next((page for page in pages if page.url_path == wanted), None)


def current_language() -> str:
    """The language code this session is rendering in."""
    raw = st.session_state.get(LANGUAGE_KEY)
    return raw if isinstance(raw, str) and raw in _LANGUAGE_CODES else get_language().value


def get_team() -> Team | None:
    """The team currently being edited, or ``None`` if nothing is loaded yet."""
    team = st.session_state.get(_TEAM)
    return team if isinstance(team, Team) else None


def set_team(team: Team, *, dirty: bool = True, new_draft: bool = False) -> None:
    """Replace the working team, invalidating any solution computed for the old one.

    Args:
        team: The new instance.
        dirty: Whether it now differs from the file it came from. A freshly loaded or
            uploaded team is clean; anything edited in the browser is not.
        new_draft: Begin a new version rather than overwriting the current one. True for the
            three *load* paths on Home, false for every edit -- otherwise each keystroke on the
            survey page would push another entry into the history (SPEC.md 14.4).
    """
    if new_draft:
        persistence.mint_new()
    st.session_state[_TEAM] = team
    st.session_state[_DIRTY] = dirty
    # A solution describes the team it was computed for and nothing else.
    st.session_state.pop(_RESULT, None)
    # Not a save -- a draft, so a reload does not cost the coach an evening (SPEC.md 14.4).
    # It never raises, and it never touches the file the team came from.
    persistence.save_draft(team)


def restore_draft() -> None:
    """Seed the session from this browser's draft, once per session and only if empty.

    Called from Home.py, which ``st.navigation`` runs on every rerun whichever page is shown,
    so one call site covers all five. The ``get_team()`` guard is what keeps it out of the way
    of anything that has already put a team in session state -- a page the coach navigated to,
    or a test that seeded one directly.

    A restored draft is dirty by definition: it is not the file on the coach's disk, and the
    unsaved-changes warning has to stay up (SPEC.md 14.4).
    """
    # Re-stamp first, and on every rerun: st.navigation strips the query string on each page
    # change, and a reload from a stripped URL would restore nothing (SPEC.md 14.4).
    persistence.stamp_url(current_language())
    if st.session_state.get(_RESTORED):
        return
    st.session_state[_RESTORED] = True
    if get_team() is not None:
        return
    team = persistence.load_draft()
    if team is not None:
        st.session_state[_TEAM] = team
        st.session_state[_DIRTY] = True
        st.session_state[_RESTORED_NOTICE] = True


def restore_version(token: str) -> bool:
    """Load an earlier version back into the session. False when it has expired.

    Not a mint: the restored version becomes current again, so editing from here overwrites it
    rather than starting a third branch.
    """
    team = persistence.restore(token)
    if team is None:
        return False
    st.session_state[_TEAM] = team
    st.session_state[_DIRTY] = True
    st.session_state.pop(_RESULT, None)
    return True


def draft_was_restored() -> bool:
    """Whether this session started from a draft, consumed once so the notice shows once."""
    return bool(st.session_state.pop(_RESTORED_NOTICE, False))


def is_dirty() -> bool:
    """Whether the working team has unsaved changes."""
    return bool(st.session_state.get(_DIRTY, False))


def mark_saved() -> None:
    """Record that the coach has downloaded the current team."""
    st.session_state[_DIRTY] = False


def get_config() -> SolverConfig:
    """The solver configuration chosen on the Lösung page; defaults until one is set."""
    config = st.session_state.get(_CONFIG)
    return config if isinstance(config, SolverConfig) else SolverConfig()


def set_config(config: SolverConfig) -> None:
    """Remember the solver configuration across pages."""
    st.session_state[_CONFIG] = config


def get_result() -> SolveResult | None:
    """The most recent solve for the current team, or ``None``.

    The ``SolveResult`` import sits after the ``None`` check on purpose: a result can only be
    in session state once a solve has run, so on the browser build -- which has no solver and
    can never hold a result -- this never reaches ``dancepartner.solver`` (SPEC.md 14).
    """
    result = st.session_state.get(_RESULT)
    if result is None:
        return None
    from dancepartner.solver import SolveResult

    return result if isinstance(result, SolveResult) else None


def set_result(result: SolveResult) -> None:
    """Store a solve so the Analyse page can read it without recomputing."""
    st.session_state[_RESULT] = result


def require_team() -> Team:
    """Return the loaded team, or stop the page with a localized hint if there is none."""
    team = get_team()
    if team is None:
        st.info(t("ui.no_team"))
        st.stop()
    return team


def require_result() -> SolveResult:
    """Return the current solve, or stop the page with a localized hint if there is none."""
    result = get_result()
    if result is None or not result.solutions:
        st.info(t("ui.no_solution_yet"))
        st.stop()
    return result


# -- solving ------------------------------------------------------------------------------


@st.cache_data(
    show_spinner=False,
    # st.cache_data cannot hash a pydantic model on its own. Both hashes are the canonical
    # serialisations the core already uses, so two teams that save identically -- and two
    # configs that serialise identically -- share a cache entry, which is exactly right.
    hash_funcs={Team: dump_team, SolverConfig: lambda c: c.model_dump_json()},
)
def cached_solve(team: Team, config: SolverConfig) -> SolveResult:
    """Solve, memoised on ``(team, config)`` as SPEC.md 10 asks.

    ``solve`` is imported here rather than at module level: it is the one thing in the core
    that reaches ortools, which the browser build has no wheel for (SPEC.md 14).

    Raises:
        InfeasibleInstanceError: The counting pre-checks rejected the instance. Callers
            render ``error.issues`` from it; see :func:`show_issues`.
    """
    from dancepartner.solver import solve

    return solve(team, config)


UI_FLUSH_SECONDS: Final = 0.05
"""How long to yield so the browser can draw what was just written. Measured, not guessed."""


def flush_ui() -> None:
    """Give the page a chance to show what has been written, before blocking on the solver.

    Streamlit hands an element to the browser as soon as it is written, and on the server that
    is the end of it. Under stlite the delivery needs the Pyodide worker's event loop, and a
    script run that goes straight from drawing a busy banner into a solve never gives it a
    turn -- so the banner arrives together with the answer, which is to say never. Sleeping is
    what yields; 50 ms is enough, measured in Chrome against a 1.3 s solve (SPEC.md 14.7).

    Harmless on the other two targets, where it costs one twentieth of a second nobody was
    going to notice, on a click that is about to take seconds.
    """
    time.sleep(UI_FLUSH_SECONDS)


def solve_and_store(team: Team, config: SolverConfig) -> None:
    """Run the cached solve into session state, or show the pre-check issues and stop.

    Lives here rather than on the page because catching ``InfeasibleInstanceError`` means
    naming it, and naming it means importing the solver -- which the browser build cannot do.
    Every solver reference in the UI therefore sits behind :data:`SOLVER_AVAILABLE`, in this
    module.
    """
    from dancepartner.solver import InfeasibleInstanceError

    flush_ui()
    # The configured time limit is what keeps the UI from hanging (SPEC.md 10).
    with st.spinner(t("solve.running")):
        try:
            set_result(cached_solve(team, config))
        except InfeasibleInstanceError as exc:
            st.error(t("solve.infeasible_precheck"))
            show_issues(list(exc.issues))
            st.stop()


# -- formatting ---------------------------------------------------------------------------


def names(team: Team, ids: list[str] | tuple[str, ...]) -> str:
    """Join dancer ids into a display string of names, or an em dash if there are none."""
    by_id = team.dancers_by_id
    return ", ".join(by_id[i].name for i in ids) if ids else t("table.nothing")


def role_label(role: Role) -> str:
    """The localized singular for a role."""
    return t(f"role.{role.value}")


def role_plural(role: Role) -> str:
    """The localized plural for a role."""
    return t(f"role.{role.value}.plural")


def rank_label(rank: int, direction: Direction) -> str:
    """The user-facing name of one preference rank, e.g. "Wish 1" / "No-go 2"."""
    return t(f"tier.{direction}", rank=rank)


def tier_summary(team: Team, tiers: dict[int, list[str]], direction: Direction) -> str:
    """Render a ``rank -> ids`` mapping as ``Wish 1: A, B; Wish 2: C``.

    ``direction`` picks the rank wording: a not-desired list must not be labelled with the
    word for a wish, which is the whole reason the label is not derived from the rank alone.
    """
    if not tiers:
        return t("table.nothing")
    return "; ".join(
        t("explain.entry", label=rank_label(rank, direction), names=names(team, ids)).strip()
        for rank, ids in sorted(tiers.items())
    )


def score_badge(score: int, worst: int, best: int) -> str:
    """A three-step colour cue for one dancer's score.

    Colour encodes satisfaction and nothing else -- never the dancer's name, never their role
    (SPEC.md 10). ``worst`` and ``best`` come from the solution being shown, so the scale is
    relative to what was actually achievable on this instance.
    """
    if best <= worst:
        return "🟩"
    position = (score - worst) / (best - worst)
    if position < 1 / 3:
        return "🟥"
    return "🟨" if position < 2 / 3 else "🟩"


def ratio_badge(ratio: float | None) -> str:
    """A three-step colour cue for one dancer's absolute satisfaction ratio (BEST mode).

    The scale is absolute -- 1.0 is "top wish fulfilled, nothing violated" -- unlike
    :func:`score_badge`, which is relative to the solution shown. ``None`` means the dancer
    stated no in-scope preference at all: neutral gets a colourless marker, never a red one.
    """
    if ratio is None:
        return "⬜"
    if ratio < 1 / 3:
        return "🟥"
    return "🟨" if ratio < 2 / 3 else "🟩"


_GROUP_MARKERS: Final = ("1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟")


def group_marker(number: int) -> str:
    """The marker for one exchange group: a number emoji, plain text past ten.

    A number, not a colour -- colour encodes satisfaction and nothing else (SPEC.md 10).
    """
    return _GROUP_MARKERS[number - 1] if 1 <= number <= len(_GROUP_MARKERS) else f"({number})"


def satisfaction_badges(satisfaction: DancerSatisfaction) -> str:
    """Inline markdown badges counting fulfilled wishes and violated dislikes."""
    parts = []
    fulfilled = sum(len(ids) for ids in satisfaction.fulfilled_desired.values())
    violated = sum(len(ids) for ids in satisfaction.violated_not_desired.values())
    if fulfilled:
        parts.append(f":green-badge[{fulfilled} {t('ui.solve.fulfilled_badge')}]")
    if violated:
        parts.append(f":red-badge[{violated} {t('ui.solve.violated_badge')}]")
    return " ".join(parts)


def objective_label(objective: Objective) -> str:
    """Localized label for an objective."""
    return t(f"ui.objective.{objective.value}")


def aggregation_label(aggregation: ScoreAggregation) -> str:
    """Localized label for a score aggregation."""
    return t(f"ui.aggregation.{aggregation.value}")


def scope_label(scope: PreferenceScope) -> str:
    """Localized label for a preference scope."""
    return t(f"ui.scope.{scope.value}")


def sense_label(sense: str) -> str:
    """Localized label for an objective stage direction."""
    return t(f"solve.sense.{sense}")


# -- tiers ---------------------------------------------------------------------------------
#
# SPEC.md 6 requires the ranks of each direction to start at 1 and be gap-free. Editing in a
# browser breaks that constantly -- a tier is emptied, a dancer is deleted out from under a
# wish -- so both editing pages funnel through these two, which drop what is empty and close
# the gaps rather than handing the coach a validation error they did not cause.


def renumber_tiers(tiers: list[Tier], known: set[str]) -> list[Tier]:
    """Drop unknown ids and empty tiers, then renumber the rest contiguously from 1.

    Relative order is preserved, so a stronger wish stays stronger.
    """
    return tiers_from_selections(
        [sorted(tier.dancer_ids & known) for tier in sorted(tiers, key=lambda t: t.rank)]
    )


def tiers_from_selections(selections: list[list[str]]) -> list[Tier]:
    """Build tiers from ordered id lists, dropping empty ones and renumbering from 1."""
    return [
        Tier(rank=rank, dancer_ids=frozenset(ids))
        for rank, ids in enumerate((s for s in selections if s), start=1)
    ]


def with_survey(team: Team, dancer_id: str, survey: Survey | None) -> Team:
    """Rebuild ``team`` with ``dancer_id``'s survey replaced, or removed when ``None``.

    Goes through the ``Team`` constructor rather than ``model_copy``: the latter skips
    validation on a frozen model, which is exactly the check we want here (SPEC.md 6 requires
    at most one survey per dancer and every referenced id to exist).

    Surveys come back in roster order so the saved YAML stays stable across edits.
    """
    kept = {s.dancer_id: s for s in team.surveys if s.dancer_id != dancer_id}
    if survey is not None:
        kept[dancer_id] = survey
    ordered = [kept[d.id] for d in team.dancers if d.id in kept]
    return Team(dancers=list(team.dancers), surveys=ordered, n_positions=team.n_positions)


# -- rendering helpers --------------------------------------------------------------------


def show_issues(issues: list[object]) -> None:
    """Render feasibility issues. ``message`` is already localized -- just print it."""
    for issue in issues:
        message = getattr(issue, "message", "")
        involved = getattr(issue, "involved_ids", ())
        team = get_team()
        if involved and team is not None:
            message = f"{message}\n\n_{t('ui.feasibility.involved', names=names(team, involved))}_"
        st.error(message)


def position_of(solution: Solution, dancer_id: str) -> str:
    """The label (A-H) of the position ``dancer_id`` sits on."""
    for position in solution.positions:
        if dancer_id in (*position.leaders, *position.followers):
            return position.label
    raise KeyError(dancer_id)


def empty_team(n_positions: int = DEFAULT_N_POSITIONS) -> Team:
    """A minimal valid team to start editing from: one couple, so the model validates."""
    return Team(
        dancers=[
            Dancer(id="herr-1", name="Herr 1", role=Role.LEADER),
            Dancer(id="dame-1", name="Dame 1", role=Role.FOLLOWER),
        ],
        n_positions=n_positions,
    )


def page_header(title_key: str, subtitle_key: str | None = None) -> None:
    """Standard page heading, plus the unsaved-changes warning when one is pending."""
    st.title(t(title_key))
    if subtitle_key:
        st.caption(t(subtitle_key))
    if is_dirty():
        st.warning(t("ui.unsaved"), icon="⚠️")
