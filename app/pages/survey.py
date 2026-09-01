"""Umfrage page: edit one dancer's survey as a dynamic list of tiers per direction.

Preferences are **directed**: A wishing for B says nothing about what B wrote. Nothing on this
page symmetrises, and nothing writes into another dancer's survey (SPEC.md 3).

The two rules validated live are SPEC.md 6 rules 3 and 4 -- an id may appear in only one tier
per direction, and never in both directions at once. They are checked here explicitly so the
conflict reads in the coach's language; pydantic remains the final gate, but its raw
message must never reach the coach.
"""

from __future__ import annotations

import streamlit as st

import common
from dancepartner.i18n import t
from dancepartner.model import Direction, Survey, Tier

common.page_header("ui.survey.header")
team = common.require_team()

_DIRECTIONS: tuple[tuple[Direction, str, str], ...] = (
    ("desired", "ui.survey.desired", "desired_tiers"),
    ("not_desired", "ui.survey.not_desired", "not_desired_tiers"),
)


def _label(dancer_id: str) -> str:
    """Name plus answered/open marker for the dancer picker."""
    answered = dancer_id in team.surveys_by_id
    marker = t("ui.survey.answered") if answered else t("ui.survey.unanswered")
    return f"{team.dancers_by_id[dancer_id].name} ({marker})"


def _tier_count_key(dancer_id: str, direction: Direction) -> str:
    return f"n_tiers_{dancer_id}_{direction}"


def _existing(survey: Survey | None, attribute: str) -> list[list[str]]:
    """The stored tiers of one direction as ordered id lists, strongest first."""
    if survey is None:
        return []
    tiers: list[Tier] = getattr(survey, attribute)
    return [sorted(tier.dancer_ids) for tier in sorted(tiers, key=lambda t: t.rank)]


def _selected_tiers(
    dancer_id: str, direction: Direction, stored: list[list[str]]
) -> list[list[str]]:
    """Render the multiselects for one direction and return what is currently selected."""
    count_key = _tier_count_key(dancer_id, direction)
    if count_key not in st.session_state:
        st.session_state[count_key] = max(len(stored), 1)
    count = int(st.session_state[count_key])

    # Everyone but the dancer themself: a self-reference is rejected by the model, and
    # offering it would invite the error rather than prevent it.
    options = [i for i in team.dancers_by_id if i != dancer_id]

    selections: list[list[str]] = []
    for index in range(count):
        default = [i for i in stored[index] if i in options] if index < len(stored) else []
        chosen = st.multiselect(
            common.rank_label(index + 1, direction),
            options=options,
            default=default,
            format_func=lambda i: team.dancers_by_id[i].name,
            key=f"tier_{dancer_id}_{direction}_{index}",
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


picked = st.selectbox(
    t("ui.survey.pick"), options=list(team.dancers_by_id), format_func=_label, index=0
)
st.caption(t("ui.survey.count", n=len(team.surveys), total=len(team.dancers)))

survey = team.surveys_by_id.get(picked)
chosen: dict[str, list[list[str]]] = {}

columns = st.columns(2)
for column, (direction, heading_key, attribute) in zip(columns, _DIRECTIONS, strict=True):
    with column:
        st.subheader(t(heading_key))
        chosen[direction] = _selected_tiers(picked, direction, _existing(survey, attribute))

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

if st.button(t("ui.survey.apply"), type="primary", disabled=bool(conflicts)):
    desired_tiers = common.tiers_from_selections(chosen["desired"])
    not_desired_tiers = common.tiers_from_selections(chosen["not_desired"])
    name = team.dancers_by_id[picked].name

    if not desired_tiers and not not_desired_tiers:
        # An empty survey is not the same as an unanswered one; drop it entirely so
        # "n von m haben geantwortet" keeps telling the truth.
        common.set_team(common.with_survey(team, picked, None))
        st.success(t("ui.survey.cleared", name=name))
        st.rerun()
    else:
        try:
            updated = Survey(
                dancer_id=picked,
                desired_tiers=desired_tiers,
                not_desired_tiers=not_desired_tiers,
            )
            team = common.with_survey(team, picked, updated)
        except ValueError as exc:
            st.error(t("error.invalid_team", detail=exc))
        else:
            common.set_team(team)
            st.success(t("ui.survey.applied", name=name))
            st.rerun()
