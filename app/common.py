"""Shared state and formatting for the Streamlit pages.

The pages are thin: they arrange widgets and call into this module, which in turn calls the
core. Nothing here re-derives a number the core already computes -- see
:mod:`dancepartner.reporting` for the derivations both the CLI and this UI share.

The dependency runs one way only. ``dancepartner`` never imports ``streamlit``; deleting
``app/`` leaves the CLI working (SPEC.md 5).
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

import streamlit as st

from dancepartner.i18n import Language, get_language, set_language, t
from dancepartner.model import (
    DEFAULT_N_POSITIONS,
    Dancer,
    Objective,
    PreferenceScope,
    Role,
    ScoreAggregation,
    SolverConfig,
    Survey,
    Team,
    Tier,
    WeightScheme,
)
from dancepartner.scoring import DancerSatisfaction, Solution
from dancepartner.solver import SolveResult, solve
from dancepartner.storage import dump_team

REPO_ROOT: Final = Path(__file__).resolve().parents[1]
EXAMPLE_TEAM: Final = REPO_ROOT / "data" / "team.example.yaml"

# -- session state ------------------------------------------------------------------------
#
# SPEC.md 10: the team lives in st.session_state and reaches disk only when the coach presses
# save. PyYAML cannot preserve comments, so an autosave would quietly strip the documentation
# out of any hand-written team file.

_TEAM: Final = "team"
_PATH: Final = "team_path"
_DIRTY: Final = "dirty"
_RESULT: Final = "result"
_CONFIG: Final = "config"
LANGUAGE_KEY: Final = "language"


def sync_language() -> None:
    """Point the core i18n layer at the language chosen in this session.

    The core language is a process-wide setting while the choice lives per browser session,
    so Home.py calls this at the top of every rerun, before anything renders a label. A fresh
    session is seeded from the environment-variable default (English when unset).
    """
    raw = st.session_state.get(LANGUAGE_KEY)
    if not isinstance(raw, str):
        raw = get_language().value
        st.session_state[LANGUAGE_KEY] = raw
    set_language(Language(raw))


def get_team() -> Team | None:
    """The team currently being edited, or ``None`` if nothing is loaded yet."""
    team = st.session_state.get(_TEAM)
    return team if isinstance(team, Team) else None


def set_team(team: Team, *, path: Path | None = None, dirty: bool = True) -> None:
    """Replace the working team, invalidating any solution computed for the old one.

    Args:
        team: The new instance.
        path: Where it came from, remembered as the default save target.
        dirty: Whether it now differs from what is on disk. A freshly loaded team is clean.
    """
    st.session_state[_TEAM] = team
    if path is not None:
        st.session_state[_PATH] = str(path)
    st.session_state[_DIRTY] = dirty
    # A solution describes the team it was computed for and nothing else.
    st.session_state.pop(_RESULT, None)


def team_path() -> str:
    """The remembered save target; empty when the team was built in the browser."""
    value = st.session_state.get(_PATH, "")
    return value if isinstance(value, str) else ""


def is_dirty() -> bool:
    """Whether the working team has unsaved changes."""
    return bool(st.session_state.get(_DIRTY, False))


def mark_saved(path: Path) -> None:
    """Record that the working team now matches the file at ``path``."""
    st.session_state[_PATH] = str(path)
    st.session_state[_DIRTY] = False


def get_config() -> SolverConfig:
    """The solver configuration chosen on the Lösung page; defaults until one is set."""
    config = st.session_state.get(_CONFIG)
    return config if isinstance(config, SolverConfig) else SolverConfig()


def set_config(config: SolverConfig) -> None:
    """Remember the solver configuration across pages."""
    st.session_state[_CONFIG] = config


def get_result() -> SolveResult | None:
    """The most recent solve for the current team, or ``None``."""
    result = st.session_state.get(_RESULT)
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

    Raises:
        InfeasibleInstanceError: The counting pre-checks rejected the instance. Callers
            render ``error.issues`` from it; see :func:`show_issues`.
    """
    return solve(team, config)


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


def tier_summary(team: Team, tiers: dict[int, list[str]]) -> str:
    """Render a ``rank -> ids`` mapping as ``Tier 1: A, B; Tier 2: C``."""
    if not tiers:
        return t("table.nothing")
    return "; ".join(
        t("explain.entry", rank=rank, names=names(team, ids)).strip()
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


def weights_label(scheme: WeightScheme) -> str:
    """Localized label for a tier weight scheme."""
    return t(f"ui.weights.{scheme.value}")


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
