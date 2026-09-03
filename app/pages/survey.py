"""Survey page: edit one dancer's survey as a dynamic list of tiers per direction.

Preferences are **directed**: A wishing for B says nothing about what B wrote. Nothing on this
page symmetrises, and nothing writes into another dancer's survey (SPEC.md 3).

The two rules validated live are SPEC.md 6 rules 3 and 4 -- an id may appear in only one tier
per direction, and never in both directions at once. They are checked here explicitly so the
conflict reads in the coach's language; pydantic remains the final gate, but its raw
message must never reach the coach.

Twenty surveys are twenty visits to this page, so the picker keeps its place: it is seeded from
``common.SURVEY_JUMP`` (set by Apply and by the Previous / Next buttons) before it is drawn,
which is what survives the widget identity changing when a dancer's marker flips from
"pending" to "answered". Unapplied selections are mirrored into ``common.PENDING_SURVEYS`` on
every run and seeded back when the dancer -- or the page -- is opened again (SPEC.md 10).
"""

from __future__ import annotations

import streamlit as st

import common
from dancepartner.i18n import t
from dancepartner.model import Direction, Survey

common.page_header("ui.survey.header")
team = common.require_team()

_DIRECTIONS: tuple[tuple[Direction, str, str], ...] = (
    ("desired", "ui.survey.desired", "desired_tiers"),
    ("not_desired", "ui.survey.not_desired", "not_desired_tiers"),
)
_PICKER: str = "survey_pick"


def _label(dancer_id: str) -> str:
    """Name plus answered/open marker for the dancer picker."""
    answered = dancer_id in team.surveys_by_id
    marker = t("ui.survey.answered") if answered else t("ui.survey.unanswered")
    return f"{team.dancers_by_id[dancer_id].name} ({marker})"


def _tier_count_key(dancer_id: str, direction: Direction) -> str:
    return f"n_tiers_{dancer_id}_{direction}"


def _selected_tiers(
    dancer_id: str, direction: Direction, source: list[list[str]]
) -> list[list[str]]:
    """Render the multiselects for one direction and return what is currently selected.

    ``source`` seeds a widget the first time it is drawn -- through its session-state key,
    never through ``default=``, so that what the coach picked afterwards is what stays.
    """
    count_key = _tier_count_key(dancer_id, direction)
    if count_key not in st.session_state:
        st.session_state[count_key] = max(len(source), 1)
    count = int(st.session_state[count_key])

    # Everyone but the dancer themself: a self-reference is rejected by the model, and
    # offering it would invite the error rather than prevent it.
    options = [i for i in team.dancers_by_id if i != dancer_id]

    selections: list[list[str]] = []
    for index in range(count):
        key = f"tier_{dancer_id}_{direction}_{index}"
        if key not in st.session_state:
            st.session_state[key] = (
                [i for i in source[index] if i in options] if index < len(source) else []
            )
        chosen = st.multiselect(
            common.rank_label(index + 1, direction),
            options=options,
            format_func=lambda i: team.dancers_by_id[i].name,
            key=key,
            help=t("ui.survey.tier_help") if index == 0 else None,
        )
        selections.append(list(chosen))
        if not chosen:
            st.caption(t("ui.survey.empty_tier", label=common.rank_label(index + 1, direction)))

    add, remove = st.columns(2)
    if add.button(t("ui.survey.add_tier"), key=f"add_{dancer_id}_{direction}"):
        st.session_state[count_key] = count + 1
        st.rerun()
    if remove.button(
        t("ui.survey.remove_tier"), key=f"remove_{dancer_id}_{direction}", disabled=count <= 1
    ):
        st.session_state[count_key] = count - 1
        st.rerun()

    return selections


def _duplicates_within(selections: list[list[str]]) -> list[str]:
    """Ids named in more than one tier of the same direction (SPEC.md 6 rule 3)."""
    seen: set[str] = set()
    clashing: set[str] = set()
    for tier in selections:
        for dancer_id in tier:
            if dancer_id in seen:
                clashing.add(dancer_id)
            seen.add(dancer_id)
    return sorted(clashing)


def _flatten(selections: list[list[str]]) -> set[str]:
    return {dancer_id for tier in selections for dancer_id in tier}


def _jump(dancer_id: str | None) -> None:
    """Open ``dancer_id`` on the next run."""
    if dancer_id is not None:
        st.session_state[common.SURVEY_JUMP] = dancer_id
        st.rerun()


# -- which dancer ------------------------------------------------------------------------------

everyone = list(team.dancers_by_id)
jump = st.session_state.pop(common.SURVEY_JUMP, None)
if jump in everyone:
    st.session_state[_PICKER] = jump
elif st.session_state.get(_PICKER) not in everyone:
    remembered = st.session_state.get(common.SURVEY_DANCER)
    st.session_state[_PICKER] = remembered if remembered in everyone else everyone[0]

picked = st.selectbox(t("ui.survey.pick"), options=everyone, format_func=_label, key=_PICKER)
st.session_state[common.SURVEY_DANCER] = picked

answered, total = common.survey_progress(team)
st.progress(answered / total if total else 0.0, text=t("ui.survey.count", n=answered, total=total))

previous, following, open_next = (
    common.neighbour(team, picked, -1),
    common.neighbour(team, picked, 1),
    common.next_unanswered(team, picked),
)
back, forward, skip = st.columns(3)
if back.button(
    t("ui.survey.prev"), key="survey_prev", disabled=previous is None, use_container_width=True
):
    _jump(previous)
if forward.button(
    t("ui.survey.next"), key="survey_next", disabled=following is None, use_container_width=True
):
    _jump(following)
if skip.button(
    t("ui.survey.next_open"),
    key="survey_next_open",
    disabled=open_next is None,
    use_container_width=True,
):
    _jump(open_next)

# -- the tiers ---------------------------------------------------------------------------------

survey = team.surveys_by_id.get(picked)
pending = st.session_state.get(common.PENDING_SURVEYS, {}).get(picked)
chosen: dict[str, list[list[str]]] = {}

columns = st.columns(2)
for column, (direction, heading_key, attribute) in zip(columns, _DIRECTIONS, strict=True):
    with column:
        st.subheader(t(heading_key))
        source = pending[direction] if pending else common.stored_tiers(survey, attribute)
        chosen[direction] = _selected_tiers(picked, direction, source)

common.track_pending_survey(team, picked, chosen)
common.refresh_pending_warnings(team)

# -- live validation (SPEC.md 6 rules 3 and 4) --------------------------------------------

conflicts: list[str] = []
for direction, _, _ in _DIRECTIONS:
    duplicated = _duplicates_within(chosen[direction])
    if duplicated:
        conflicts.append(
            t("ui.survey.duplicate_in_direction", names=common.names(team, duplicated))
        )

both = sorted(_flatten(chosen["desired"]) & _flatten(chosen["not_desired"]))
if both:
    conflicts.append(t("ui.survey.in_both_directions", names=common.names(team, both)))

for conflict in conflicts:
    st.error(conflict)

# -- apply ---------------------------------------------------------------------------------

if picked in common.pending_survey_ids(team):
    st.caption(t("ui.survey.pending_here", name=team.dancers_by_id[picked].name))

if st.button(t("ui.survey.apply"), type="primary", disabled=bool(conflicts)):
    desired_tiers = common.tiers_from_selections(chosen["desired"])
    not_desired_tiers = common.tiers_from_selections(chosen["not_desired"])
    name = team.dancers_by_id[picked].name

    if not desired_tiers and not not_desired_tiers:
        # An empty survey is not the same as an unanswered one; drop it entirely so
        # "n of m have answered" keeps telling the truth.
        updated_team = common.with_survey(team, picked, None)
        notice = t("ui.survey.cleared", name=name)
    else:
        try:
            updated_team = common.with_survey(
                team,
                picked,
                Survey(
                    dancer_id=picked,
                    desired_tiers=desired_tiers,
                    not_desired_tiers=not_desired_tiers,
                ),
            )
        except ValueError as exc:
            st.error(t("error.invalid_team", detail=exc))
            st.stop()
        notice = t("ui.survey.applied", name=name)

    common.set_team(updated_team)
    remaining = dict(st.session_state.get(common.PENDING_SURVEYS, {}))
    remaining.pop(picked, None)
    st.session_state[common.PENDING_SURVEYS] = remaining
    common.flash("success", notice)
    # Stay on this dancer: the marker in their label just changed, which changes the widget.
    _jump(picked)
