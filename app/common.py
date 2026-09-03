"""Shared state and formatting for the Streamlit pages.

The pages are thin: they arrange widgets and call into this module, which in turn calls the
core. Nothing here re-derives a number the core already computes -- see
:mod:`dancepartner.reporting` for the derivations both the CLI and this UI share.

The dependency runs one way only. ``dancepartner`` never imports ``streamlit``; deleting
``app/`` leaves the CLI working (SPEC.md 5).
"""

from __future__ import annotations

import csv
import io
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import streamlit as st
from streamlit.delta_generator import DeltaGenerator
from streamlit.navigation.page import StreamlitPage

import persistence
from dancepartner.feasibility import FeasibilityIssue, check_feasibility
from dancepartner.i18n import Language, get_language, set_language, t
from dancepartner.model import (
    DEFAULT_N_POSITIONS,
    CoachConstraints,
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
from dancepartner.reporting import (
    exchange_groups,
    group_numbers,
    positions_by_dancer,
    satisfaction_ratio,
)
from dancepartner.scoring import DancerSatisfaction, Solution
from dancepartner.solver import available_backends
from dancepartner.storage import MalformedYamlError, StorageError, dump_team, parse_team

if TYPE_CHECKING:  # Importing the solver for real would pull in ortools -- see SOLVER_AVAILABLE.
    from dancepartner.solver import SolveResult

SOLVER_AVAILABLE: Final = bool(available_backends())
"""Whether an assignment can be computed here.

Asked of the dispatcher rather than of one package: there are two backends, and the browser
build solves with the second of them, HiGHS (SPEC.md 8.1). ``available_backends`` probes with
``find_spec``, so asking costs nothing and never drags a solver in.

It is normally true everywhere, including in the browser. It goes false only where neither
ortools nor highspy is installed -- a core-only install, say -- and then the Solution page says
so instead of failing.
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
_PAGES: Final = "nav_pages"
_FLASHES: Final = "flashes"
_LAST_UPLOAD: Final = "last_upload_id"

# Edits the coach has made but not yet applied. They live in plain session-state keys because
# Streamlit drops a widget's state as soon as a run does not render it -- opening another page
# would otherwise throw half an hour of roster entry away without a word (SPEC.md 10).
PENDING_ROSTER: Final = "pending_roster"
ROSTER_BASE: Final = "roster_base"
PENDING_N_POSITIONS: Final = "pending_n_positions"
PENDING_RULES: Final = "pending_rules"
PENDING_SURVEYS: Final = "pending_surveys"
SURVEY_DANCER: Final = "survey_dancer"
SURVEY_JUMP: Final = "survey_jump"
SOLUTION_INDEX_KEY: Final = "solution_index"
"""The shortlist entry every tab of the Solution page shows. One picker, one solution."""
_HEADER_SLOT: Final = "pending_header_slot"
_SIDEBAR_SLOT: Final = "pending_sidebar_slot"
"""Placeholders for the unapplied-edits warnings, refilled by the editing pages once they know.

Both are drawn before the page's widgets exist, so what they say at that point is one run old.
An editing page calls :func:`refresh_pending_warnings` after mirroring its widgets and the
warnings catch up within the same run -- no lag, no extra rerun.
"""

_PENDING_KEYS: Final = (
    PENDING_ROSTER,
    ROSTER_BASE,
    PENDING_N_POSITIONS,
    PENDING_RULES,
    PENDING_SURVEYS,
    SURVEY_DANCER,
    SURVEY_JUMP,
)
# Widget keys the editing pages seed from the pending state. Cleared with it, so a freshly
# loaded team is never shown through the previous team's half-edited widgets.
_PAGE_WIDGET_KEYS: Final = ("team_editor", "n_positions", "coach_pick", "coach_kind", "survey_pick")
_PAGE_WIDGET_PREFIXES: Final = ("tier_", "n_tiers_")


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
        # Whatever was half-edited belonged to the previous team.
        clear_pending()
    st.session_state[_TEAM] = team
    st.session_state[_DIRTY] = dirty
    # A solution describes the team it was computed for and nothing else.
    st.session_state.pop(_RESULT, None)
    # Not a save -- a draft, so a reload does not cost the coach an evening (SPEC.md 14.4).
    # It never raises, and it never touches the file the team came from.
    persistence.save_draft(team)
    if new_draft:
        # A new version starts out with the settings currently chosen, so a reload of it
        # brings both back together.
        persistence.save_config(get_config())


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
        config = persistence.load_config()
        if config is not None:
            st.session_state[_CONFIG] = config


def restore_version(token: str) -> bool:
    """Load an earlier version back into the session. False when it has expired.

    Not a mint: the restored version becomes current again, so editing from here overwrites it
    rather than starting a third branch.
    """
    team = persistence.restore(token)
    if team is None:
        return False
    clear_pending()
    st.session_state[_TEAM] = team
    st.session_state[_DIRTY] = True
    st.session_state[_CONFIG] = persistence.load_config(token) or SolverConfig()
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
    """The solver configuration chosen on the Solution page; defaults until one is set."""
    config = st.session_state.get(_CONFIG)
    return config if isinstance(config, SolverConfig) else SolverConfig()


def set_config(config: SolverConfig) -> None:
    """Remember the solver configuration across pages, and beside the draft.

    The Solution page calls this on every rerun, so the sidecar is only written when the value
    actually moved -- on the browser build every write reaches IndexedDB.
    """
    if st.session_state.get(_CONFIG) != config:
        persistence.save_config(config)
    st.session_state[_CONFIG] = config


def get_result() -> SolveResult | None:
    """The most recent solve for the current team, or ``None``.

    The ``SolveResult`` import sits after the ``None`` check on purpose: a result can only be
    in session state once a solve has run, so a page that merely asks keeps this module's
    import graph free of the dispatcher (SPEC.md 14.2).
    """
    result = st.session_state.get(_RESULT)
    if result is None:
        return None
    from dancepartner.solver import SolveResult

    return result if isinstance(result, SolveResult) else None


def set_result(result: SolveResult) -> None:
    """Store a solve for the Solution page's tabs, and start them on its best entry.

    Called before the picker widget is instantiated in the same run, so resetting its key is
    allowed.
    """
    st.session_state[_RESULT] = result
    st.session_state.pop(SOLUTION_INDEX_KEY, None)


def require_team() -> Team:
    """Return the loaded team, or stop the page with a localized hint if there is none."""
    team = get_team()
    if team is None:
        st.info(t("ui.no_team"))
        st.stop()
    return team


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
    return Team(
        dancers=list(team.dancers),
        surveys=ordered,
        n_positions=team.n_positions,
        coach_constraints=team.coach_constraints,
    )


def with_coach_constraints(team: Team, constraints: CoachConstraints) -> Team:
    """Rebuild ``team`` with the coach's rules replaced.

    Through the constructor, never ``model_copy`` -- same reason as :func:`with_survey`: the
    rules may only name dancers who exist, and that check lives in the validator.
    """
    return Team(
        dancers=list(team.dancers),
        surveys=list(team.surveys),
        n_positions=team.n_positions,
        coach_constraints=constraints,
    )


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
    """Standard page heading, then what the coach must not lose sight of.

    Parked notices first (the outcome of the click that caused this rerun), then the
    unsaved-changes warning, then the unapplied-edits warnings -- on every page, because the
    edits are pending on a page the coach may just have left.
    """
    st.title(t(title_key))
    if subtitle_key:
        st.caption(t(subtitle_key))
    render_flashes()
    if is_dirty():
        st.warning(t("ui.unsaved"), icon="⚠️")
    team = get_team()
    if team is not None:
        slot = st.empty()
        st.session_state[_HEADER_SLOT] = slot
        _fill_pending(slot, team, compact=False)


def render_feasibility(team: Team, config: SolverConfig) -> list[FeasibilityIssue]:
    """The counting pre-check (SPEC.md 7) with its verdict and caveat, returning the issues.

    Takes the config explicitly because the verdict depends on it: ``veto_tier`` and ``scope``
    decide which no-gos count as walls. The Solution page draws it next to those very widgets;
    Home shows the same verdict read-only and says which settings it assumes.
    """
    issues = list(check_feasibility(team, config))
    if issues:
        st.markdown(t("check.issues", count=len(issues)))
        show_issues(list(issues))
    else:
        st.success(t("check.ok"))
    st.caption(t("check.caveat"))
    return issues


# -- notices across a rerun -----------------------------------------------------------------
#
# st.rerun throws the current run away, so a message written just before it is never drawn.
# Anything that reruns parks its message here, and page_header draws it at the top of the
# next run (SPEC.md 10).


def flash(level: str, message: str) -> None:
    """Park a notice for the next run. ``level`` is ``success``, ``info`` or ``warning``."""
    flashes = list(st.session_state.get(_FLASHES, []))
    flashes.append((level, message))
    st.session_state[_FLASHES] = flashes


def render_flashes() -> None:
    """Draw and forget the parked notices."""
    renderers = {"success": st.success, "info": st.info, "warning": st.warning}
    for level, message in st.session_state.pop(_FLASHES, []):
        renderers.get(level, st.info)(message)


# -- loading a team -------------------------------------------------------------------------
#
# The three ways in. Each is a *load*, so each starts a new version (SPEC.md 14.4). They live
# here because two places offer them: the sidebar on every page, and Home while nothing is
# loaded yet.


def load_example() -> bool:
    """Load the bundled example team, reporting failures through i18n. True on success."""
    path = EXAMPLE_TEAM
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
        set_team(team, dirty=False, new_draft=True)
        return True
    return False


def load_uploaded(data: bytes) -> bool:
    """Load a team from an uploaded file, reporting failures through i18n. True on success."""
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
        # button is the only way back out (there is no path on this machine to overwrite).
        set_team(team, dirty=False, new_draft=True)
        return True
    return False


def create_team() -> bool:
    """Start a fresh team with the default number of positions, and say where to change it.

    No positions input here: the Team page is the one place that edits ``n_positions``, so
    two widgets can never disagree about it.
    """
    set_team(empty_team(), new_draft=True)
    flash("info", t("ui.home.created", n_positions=DEFAULT_N_POSITIONS))
    return True


def render_load_controls(prefix: str, *, columns: bool) -> None:
    """Upload, new team, example -- side by side on Home, stacked in the sidebar.

    ``prefix`` keeps the two instances' widget keys apart. One shared upload guard is enough:
    file ids are unique, so neither uploader can re-fire on a file the other already loaded.

    A successful load reruns the script: the sidebar above these controls has already been
    drawn for the previous team, and a parked notice is only shown by the next run.
    """
    slots = st.columns(3) if columns else [st.container(), st.container(), st.container()]
    with slots[0]:
        st.markdown(f"**{t('ui.load.upload')}**")
        upload = st.file_uploader(
            t("ui.load.uploader"), type=["yaml", "yml"], key=f"{prefix}_upload"
        )
        # `upload is not None` stays true for as long as the file sits in the widget, so this
        # branch re-fires on every rerun. Acting on it unguarded would mint a fresh version --
        # and re-clobber the coach's edits with the file -- once per rerun.
        if upload is not None and st.session_state.get(_LAST_UPLOAD) != upload.file_id:
            st.session_state[_LAST_UPLOAD] = upload.file_id
            if load_uploaded(upload.getvalue()):
                st.rerun()
    with slots[1]:
        st.markdown(f"**{t('ui.load.create')}**")
        if (
            st.button(
                t("ui.load.create_button"), key=f"{prefix}_new_team", use_container_width=True
            )
            and create_team()
        ):
            st.rerun()
    with slots[2]:
        st.markdown(f"**{t('ui.load.example')}**")
        st.caption(t("ui.load.example_hint"))
        if (
            st.button(
                t("ui.load.example_button"), key=f"{prefix}_load_example", use_container_width=True
            )
            and load_example()
        ):
            st.rerun()


# -- the sidebar workspace ------------------------------------------------------------------
#
# Everything about the *file* -- language, what is loaded, whether it is saved, how to save
# it, how to load another, how to get an earlier version back -- on every page. The coach's
# last step is a download, and it must not require walking back to the first page.


def register_pages(pages: dict[str, StreamlitPage]) -> None:
    """Make the navigation's pages known to :func:`page_link`."""
    st.session_state[_PAGES] = pages


def page_link(name: str) -> None:
    """A link to one of the registered pages, or nothing when there is no navigation.

    ``st.page_link`` raises for a page the navigation does not know, and a page file run on its
    own (``AppTest`` does that) registers only itself -- so the link is skipped rather than
    let fail.
    """
    pages = st.session_state.get(_PAGES)
    if isinstance(pages, dict) and name in pages:
        st.page_link(pages[name])


def render_sidebar(pages: dict[str, StreamlitPage]) -> None:
    """Draw the workspace and the page menu. Called from Home.py before the page runs.

    Order matters twice over. It runs before any page widget, which is what allows a load or
    a restore here to clear the editing pages' widget keys (:func:`clear_pending`). And the
    warnings sit above the download button they are asking the coach to press.
    """
    register_pages(pages)
    with st.sidebar:
        for page in pages.values():
            st.page_link(page)
        st.divider()
        team = get_team()
        if team is None:
            st.caption(t("ui.sidebar.no_team"))
        else:
            summary = t(
                "ui.sidebar.team", n_dancers=len(team.dancers), n_positions=team.n_positions
            )
            st.markdown(f"**{summary}**")
            slot = st.empty()
            st.session_state[_SIDEBAR_SLOT] = slot
            _fill_pending(slot, team, compact=True)
            if is_dirty():
                st.warning(t("ui.sidebar.unsaved"), icon="⚠️")
            # The only export of the team, and the only thing that clears the warning above.
            # PyYAML drops comments, hence the help text -- and hence no autosave (SPEC.md 9).
            st.download_button(
                t("ui.save.download"),
                data=dump_team(team),
                file_name=DOWNLOAD_NAME,
                mime="application/yaml",
                type="primary",
                use_container_width=True,
                key="sb_download",
                help=t("ui.save.comment_warning"),
                on_click=mark_saved,
            )
        with st.popover(t("ui.sidebar.load"), use_container_width=True):
            render_load_controls("sb", columns=False)
            st.caption(t("ui.draft.hint"))
        _render_history()

        st.selectbox(
            t("ui.language"),
            options=[language.value for language in Language],
            format_func=lambda code: t(f"language.{code}"),
            key=LANGUAGE_KEY,
        )


def _render_history() -> None:
    """Earlier versions with a way back to each, and the button that forgets them all.

    The browser's back button would be the obvious control and is not available: in a
    ``st.navigation`` app a back press leaves ``st.query_params`` reporting the newest value
    (streamlit#13963), so the app cannot tell which version the URL points at. An explicit list
    does not depend on that, and it works the same on both targets -- see app/persistence.py.
    """
    if not persistence.has_draft():
        return
    with st.expander(t("ui.draft.history")):
        st.caption(t("ui.draft.history_hint"))
        for entry in persistence.history():
            label, button = st.columns([3, 1])
            when = datetime.fromtimestamp(entry.saved_at).strftime("%H:%M")
            label.write(t("ui.draft.entry", n=entry.n_dancers, when=when))
            if button.button(t("ui.draft.restore"), key=f"restore_{entry.token}"):
                if restore_version(entry.token):
                    flash("success", t("ui.draft.restored_version"))
                    st.rerun()
                else:
                    st.warning(t("ui.draft.gone"))
        if st.button(t("ui.draft.discard"), key="sb_discard"):
            persistence.clear_draft()
            st.success(t("ui.draft.discarded"))


# -- unapplied edits ------------------------------------------------------------------------
#
# Explicit apply everywhere, one mental model (SPEC.md 10): nothing reaches the team until the
# coach presses the button, and nothing typed is lost before that -- not by opening another
# page, not by switching the language. The editing pages copy their widgets' current values
# into these keys on every run and seed the widgets back from them on the next mount.


def clear_pending() -> None:
    """Forget every unapplied edit and the widget state seeded from it.

    Only safe before the editing pages' widgets have been instantiated in the current run,
    which is where its callers sit: the sidebar, and Home.
    """
    for key in _PENDING_KEYS:
        st.session_state.pop(key, None)
    for widget_key in list(st.session_state):
        name = str(widget_key)
        if name in _PAGE_WIDGET_KEYS or name.startswith(_PAGE_WIDGET_PREFIXES):
            del st.session_state[widget_key]


def roster_records(team: Team) -> list[dict[str, Any]]:
    """The roster as field-named rows -- the shape the pending state keeps.

    Field names rather than translated headings, so a language switch mid-edit cannot leave
    the pending rows keyed in the other language.
    """
    return [
        {
            "id": dancer.id,
            "name": dancer.name,
            "role": dancer.role.value,
            "is_pole_position": dancer.is_pole_position,
            "needs_coaching": dancer.needs_coaching,
        }
        for dancer in team.dancers
    ]


def rules_of(team: Team) -> list[tuple[str, frozenset[str]]]:
    """Every coach rule as a (kind, ids) pair, together first, in stored order."""
    return [
        *(("together", group) for group in team.coach_constraints.together),
        *(("apart", group) for group in team.coach_constraints.apart),
    ]


def _same_rules(
    left: list[tuple[str, frozenset[str]]], right: list[tuple[str, frozenset[str]]]
) -> bool:
    def canonical(rules: list[tuple[str, frozenset[str]]]) -> list[tuple[str, tuple[str, ...]]]:
        return sorted((kind, tuple(sorted(group))) for kind, group in rules)

    return canonical(left) == canonical(right)


def roster_pending(team: Team) -> bool:
    """Whether the Team page holds anything -- rows, positions, rules -- not yet applied."""
    state = st.session_state
    if PENDING_ROSTER in state and state[PENDING_ROSTER] != roster_records(team):
        return True
    if PENDING_N_POSITIONS in state and int(state[PENDING_N_POSITIONS]) != team.n_positions:
        return True
    return PENDING_RULES in state and not _same_rules(state[PENDING_RULES], rules_of(team))


def stored_tiers(survey: Survey | None, attribute: str) -> list[list[str]]:
    """One direction of a stored survey as ordered id lists, strongest first."""
    if survey is None:
        return []
    tiers: list[Tier] = getattr(survey, attribute)
    return [sorted(tier.dancer_ids) for tier in sorted(tiers, key=lambda tier: tier.rank)]


_ATTRIBUTE_OF: Final = {"desired": "desired_tiers", "not_desired": "not_desired_tiers"}


def track_pending_survey(team: Team, dancer_id: str, chosen: dict[str, list[list[str]]]) -> None:
    """Remember ``dancer_id``'s current selections if they differ from the stored survey.

    Identical to what is stored means nothing is pending, so the entry is dropped again --
    otherwise merely opening a dancer would raise a warning.
    """
    pending = dict(st.session_state.get(PENDING_SURVEYS, {}))
    current = {
        direction: [sorted(tier) for tier in tiers if tier] for direction, tiers in chosen.items()
    }
    survey = team.surveys_by_id.get(dancer_id)
    stored = {
        direction: stored_tiers(survey, attribute) for direction, attribute in _ATTRIBUTE_OF.items()
    }
    if current == stored:
        pending.pop(dancer_id, None)
    else:
        pending[dancer_id] = current
    st.session_state[PENDING_SURVEYS] = pending


def pending_survey_ids(team: Team) -> list[str]:
    """Dancers with unapplied survey edits, in roster order."""
    pending = st.session_state.get(PENDING_SURVEYS, {})
    return [dancer_id for dancer_id in team.dancers_by_id if dancer_id in pending]


def prune_pending_surveys(known: set[str]) -> None:
    """After a roster apply: drop pending edits of deleted dancers, and deleted ids inside them."""
    pending = st.session_state.get(PENDING_SURVEYS)
    if not isinstance(pending, dict):
        return
    st.session_state[PENDING_SURVEYS] = {
        dancer_id: {
            direction: [[i for i in tier if i in known] for tier in tiers]
            for direction, tiers in selections.items()
        }
        for dancer_id, selections in pending.items()
        if dancer_id in known
    }


def pending_count(team: Team) -> int:
    """How many places hold unapplied edits: the Team page counts once, each survey once."""
    return int(roster_pending(team)) + len(pending_survey_ids(team))


def render_pending_warnings(team: Team) -> None:
    """One warning per place with unapplied edits."""
    if roster_pending(team):
        st.warning(t("ui.pending.roster"), icon="✏️")
    ids = pending_survey_ids(team)
    if ids:
        st.warning(t("ui.pending.surveys", names=names(team, ids)), icon="✏️")


def _fill_pending(slot: DeltaGenerator, team: Team, *, compact: bool) -> None:
    """(Re)draw one placeholder: the count for the sidebar, the full warnings for a page."""
    slot.empty()
    count = pending_count(team)
    if not count:
        return
    with slot.container():
        if compact:
            st.warning(t("ui.pending.sidebar", n=count), icon="✏️")
        else:
            render_pending_warnings(team)


def refresh_pending_warnings(team: Team) -> None:
    """Bring the header and sidebar warnings up to date with what the page just mirrored."""
    for key, compact in ((_HEADER_SLOT, False), (_SIDEBAR_SLOT, True)):
        slot = st.session_state.get(key)
        if isinstance(slot, DeltaGenerator):
            _fill_pending(slot, team, compact=compact)


# -- walking through the survey --------------------------------------------------------------


def survey_progress(team: Team) -> tuple[int, int]:
    """Answered surveys and dancers, for the progress bar."""
    return len(team.surveys), len(team.dancers)


def neighbour(team: Team, current: str, step: int) -> str | None:
    """The dancer ``step`` places from ``current`` in roster order; ``None`` past either end."""
    ids = list(team.dancers_by_id)
    if current not in ids:
        return None
    index = ids.index(current) + step
    return ids[index] if 0 <= index < len(ids) else None


def next_unanswered(team: Team, after: str | None) -> str | None:
    """The next dancer without a survey, wrapping around; ``None`` when nobody else is open."""
    ids = list(team.dancers_by_id)
    if after is None or after not in ids:
        return next((i for i in ids if i not in team.surveys_by_id), None)
    start = ids.index(after)
    around = ids[start + 1 :] + ids[:start]
    return next((i for i in around if i not in team.surveys_by_id), None)


# -- exporting a solution -------------------------------------------------------------------


def solution_csv(solution: Solution, team: Team, config: SolverConfig) -> str:
    """One row per dancer: position, name, role, id, score, satisfaction, exchange group.

    Per dancer rather than per position because a position holds one or two of each role: a
    per-position row would need variable columns and could not carry a per-dancer score. This
    shape sorts and filters in any spreadsheet, and it is what ends up on the noticeboard.
    Headers go through i18n like every other user-facing string.
    """
    places = positions_by_dancer(solution)
    numbers = group_numbers(exchange_groups(solution, team, config))
    best_mode = config.aggregation is ScoreAggregation.BEST
    roles = list(Role)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            t("ui.analysis.col_position"),
            t("table.col_name"),
            t("ui.team.col_role"),
            t("ui.team.col_id"),
            t("table.col_score"),
            t("ui.analysis.col_satisfaction"),
            t("ui.analysis.col_group"),
        ]
    )
    ordered = sorted(team.dancers, key=lambda d: (places[d.id], roles.index(d.role), d.name))
    for dancer in ordered:
        satisfaction = solution.per_dancer[dancer.id]
        percent = ""
        if best_mode:
            ratio = satisfaction_ratio(team, config, dancer.id, satisfaction)
            percent = "" if ratio is None else str(round(ratio * 100))
        writer.writerow(
            [
                places[dancer.id],
                dancer.name,
                role_label(dancer.role),
                dancer.id,
                satisfaction.score,
                percent,
                numbers.get(dancer.id, ""),
            ]
        )
    return buffer.getvalue()
