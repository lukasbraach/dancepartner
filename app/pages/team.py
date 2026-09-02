"""Team page: edit the roster in a table.

The column headings the coach reads come from i18n like every other user-facing string; the
underlying fields keep their English names (SPEC.md 2, 3).
"""

from __future__ import annotations

from typing import Any

import streamlit as st

import common
from dancepartner.i18n import t
from dancepartner.model import CoachConstraints, Dancer, Role, Survey, Team

common.page_header("ui.team.header")
team = common.require_team()

_ROLE_LABELS = {common.role_label(role): role for role in Role}

# Written out rather than built from the kind name: a t(f"ui.team.kind_{kind}") would read as
# an unused key to the scanner in tests/test_app.py, the same reason _ROLE_LABELS exists.
_KIND_LABELS = {
    t("ui.team.kind_together"): "together",
    t("ui.team.kind_apart"): "apart",
}


def _rows(source: Team) -> list[dict[str, Any]]:
    """The roster as plain dicts.

    Deliberately not a DataFrame: SPEC.md 4 keeps pandas out unless a milestone needs it, and
    ``st.data_editor`` round-trips a list of dicts perfectly well.
    """
    return [
        {
            t("ui.team.col_id"): dancer.id,
            t("ui.team.col_name"): dancer.name,
            t("ui.team.col_role"): common.role_label(dancer.role),
            t("ui.team.col_pole_position"): dancer.is_pole_position,
            t("ui.team.col_coaching"): dancer.needs_coaching,
        }
        for dancer in source.dancers
    ]


def _to_dancers(rows: list[dict[str, Any]]) -> tuple[list[Dancer], list[str]]:
    """Turn edited rows back into dancers, collecting localized errors instead of raising."""
    dancers: list[Dancer] = []
    errors: list[str] = []
    seen: set[str] = set()

    for number, row in enumerate(rows, start=1):
        dancer_id = str(row.get(t("ui.team.col_id")) or "").strip()
        name = str(row.get(t("ui.team.col_name")) or "").strip()
        if not dancer_id or not name:
            errors.append(t("ui.team.empty_field", row=number))
            continue
        if dancer_id in seen:
            errors.append(t("ui.team.duplicate_id", dancer_id=dancer_id))
            continue
        seen.add(dancer_id)

        role = _ROLE_LABELS.get(str(row.get(t("ui.team.col_role"))), Role.LEADER)
        pole = bool(row.get(t("ui.team.col_pole_position")))
        coaching = bool(row.get(t("ui.team.col_coaching")))
        if pole and coaching:
            # Report it through i18n rather than letting pydantic raise its raw message.
            errors.append(t("ui.team.flags_exclusive", name=name))
            continue

        dancers.append(
            Dancer(
                id=dancer_id,
                name=name,
                role=role,
                is_pole_position=pole,
                needs_coaching=coaching,
            )
        )
    return dancers, errors


def _surviving_surveys(source: Team, dancers: list[Dancer]) -> tuple[list[Survey], int]:
    """Drop surveys, and references inside them, that name a dancer who no longer exists."""
    known = {dancer.id for dancer in dancers}
    kept: list[Survey] = []
    for survey in source.surveys:
        if survey.dancer_id not in known:
            continue
        desired = [t for t in survey.desired_tiers if (t.dancer_ids & known)]
        not_desired = [t for t in survey.not_desired_tiers if (t.dancer_ids & known)]
        kept.append(
            Survey(
                dancer_id=survey.dancer_id,
                desired_tiers=common.renumber_tiers(desired, known),
                not_desired_tiers=common.renumber_tiers(not_desired, known),
            )
        )
    return kept, len(source.surveys) - len(kept)


def _surviving_constraints(source: Team, dancers: list[Dancer]) -> tuple[CoachConstraints, int]:
    """Drop coach rules that name a dancer who no longer exists.

    A rule is not repaired by shrinking it: "keep these three together" minus one dancer is a
    different rule, and silently keeping the remainder would be a decision the coach never
    made. A group is only kept when every id in it survived.
    """
    known = {dancer.id for dancer in dancers}
    kept: dict[str, list[frozenset[str]]] = {}
    dropped = 0
    for key, groups in (
        ("together", source.coach_constraints.together),
        ("apart", source.coach_constraints.apart),
    ):
        surviving = [group for group in groups if group <= known]
        dropped += len(groups) - len(surviving)
        kept[key] = surviving
    return CoachConstraints(together=kept["together"], apart=kept["apart"]), dropped


edited = st.data_editor(
    _rows(team),
    num_rows="dynamic",
    use_container_width=True,
    hide_index=True,
    column_config={
        t("ui.team.col_id"): st.column_config.TextColumn(t("ui.team.col_id"), required=True),
        t("ui.team.col_name"): st.column_config.TextColumn(t("ui.team.col_name"), required=True),
        t("ui.team.col_role"): st.column_config.SelectboxColumn(
            t("ui.team.col_role"), options=list(_ROLE_LABELS), required=True
        ),
        t("ui.team.col_pole_position"): st.column_config.CheckboxColumn(
            t("ui.team.col_pole_position"), help=t("ui.team.help_pole_position")
        ),
        t("ui.team.col_coaching"): st.column_config.CheckboxColumn(
            t("ui.team.col_coaching"), help=t("ui.team.help_coaching")
        ),
    },
    key="team_editor",
)

n_positions = st.number_input(
    t("ui.load.n_positions"), min_value=1, max_value=26, value=team.n_positions
)

# What the last apply had to say, carried across the rerun below. `st.rerun` throws the
# current run away, so anything written just before it is never drawn -- the notices have to
# survive in session state and be rendered at the top of the next run instead.
_NOTICES = "team_notices"

for level, message in st.session_state.pop(_NOTICES, []):
    (st.info if level == "info" else st.success)(message)

if st.button(t("ui.team.apply"), type="primary"):
    dancers, errors = _to_dancers(list(edited))
    for error in errors:
        st.error(error)
    if not errors:
        surveys, dropped = _surviving_surveys(team, dancers)
        constraints, dropped_rules = _surviving_constraints(team, dancers)
        try:
            updated = Team(
                dancers=dancers,
                surveys=surveys,
                n_positions=int(n_positions),
                coach_constraints=constraints,
            )
        except ValueError as exc:
            st.error(t("error.invalid_team", detail=exc))
        else:
            common.set_team(updated)
            notices = []
            if dropped:
                notices.append(("info", t("ui.team.orphan_survey", n=dropped)))
            if dropped_rules:
                notices.append(("info", t("ui.team.coach_orphan", n=dropped_rules)))
            notices.append(("success", t("ui.team.applied", n=len(dancers))))
            st.session_state[_NOTICES] = notices
            st.rerun()


# -- coach rules (SPEC.md 8, 7.) -----------------------------------------------------------
#
# Below the roster on purpose: the rules name dancers from the table above, and deleting a
# dancer prunes them in the same apply step.

st.subheader(t("ui.team.coach_header"))
st.caption(t("ui.team.coach_help"))

_NAMES = {dancer.id: dancer.name for dancer in team.dancers}
_KIND_OF = {"together": t("ui.team.kind_together"), "apart": t("ui.team.kind_apart")}


def _groups(source: Team) -> list[tuple[str, frozenset[str]]]:
    """Every rule as a (kind, ids) pair, together first, in stored order."""
    return [
        *(("together", group) for group in source.coach_constraints.together),
        *(("apart", group) for group in source.coach_constraints.apart),
    ]


def _without(source: Team, kind: str, group: frozenset[str]) -> CoachConstraints:
    """The rules with one group removed."""
    together = list(source.coach_constraints.together)
    apart = list(source.coach_constraints.apart)
    (together if kind == "together" else apart).remove(group)
    return CoachConstraints(together=together, apart=apart)


def _with(source: Team, kind: str, group: frozenset[str]) -> CoachConstraints:
    """The rules with one group added."""
    together = list(source.coach_constraints.together)
    apart = list(source.coach_constraints.apart)
    (together if kind == "together" else apart).append(group)
    return CoachConstraints(together=together, apart=apart)


rules = _groups(team)
if not rules:
    st.caption(t("ui.team.coach_none"))
for index, (kind, group) in enumerate(rules):
    text, button = st.columns([5, 1])
    members = ", ".join(_NAMES[i] for i in team.dancers_by_id if i in group)
    text.markdown(f"**{_KIND_OF[kind]}** — {members}")
    if button.button(t("ui.team.coach_remove"), key=f"coach_remove_{index}"):
        common.set_team(common.with_coach_constraints(team, _without(team, kind, group)))
        st.rerun()

kind_label = st.selectbox(t("ui.team.coach_kind"), options=list(_KIND_LABELS))
picked = st.multiselect(
    t("ui.team.coach_dancers"),
    options=list(_NAMES),
    format_func=lambda dancer_id: _NAMES[dancer_id],
    key="coach_pick",
)

if st.button(t("ui.team.coach_add")):
    new_kind = _KIND_LABELS[kind_label]
    new_group = frozenset(picked)
    # Checked here, in the coach's language: pydantic would raise the same two rules in
    # English, and its message must never reach the coach (SPEC.md 10).
    if len(new_group) < 2:
        st.error(t("ui.team.coach_too_small"))
    elif any(new_group == group for k, group in rules if k == new_kind):
        st.error(t("ui.team.coach_duplicate"))
    else:
        common.set_team(common.with_coach_constraints(team, _with(team, new_kind, new_group)))
        st.session_state[_NOTICES] = [("success", t("ui.team.coach_added"))]
        st.rerun()
