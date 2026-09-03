"""Team page: the roster, the number of positions and the coach's rules -- one Apply for all.

Nothing on this page reaches the team until the coach presses Apply, and nothing typed before
that is lost by opening another page: the editor's rows, the positions count and the rules are
mirrored into plain session-state keys on every run and seeded back on the next mount
(``common.PENDING_*``, SPEC.md 10).

The one Streamlit fact that shapes the mount logic: ``st.data_editor`` with dynamic rows takes
its widget identity from the data it is fed, so changing that data resets every edit. The rows
fed in are therefore frozen in ``ROSTER_BASE`` for as long as the editor is mounted, and only
re-derived -- from the pending rows -- when it mounts afresh or the language changes.

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
_LABEL_OF_ROLE = {role.value: label for label, role in _ROLE_LABELS.items()}
_ROLE_VALUES = {role.value for role in Role}

# Written out rather than built from the kind name: a t(f"ui.team.kind_{kind}") would read as
# an unused key to the scanner in tests/test_app.py, the same reason _ROLE_LABELS exists.
_KIND_LABELS = {
    t("ui.team.kind_together"): "together",
    t("ui.team.kind_apart"): "apart",
}
_KIND_OF = {kind: label for label, kind in _KIND_LABELS.items()}

# -- the roster ---------------------------------------------------------------------------------


def _rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Field-named records as the editor's rows, headed in the coach's language.

    Deliberately not a DataFrame: SPEC.md 4 keeps pandas out unless a milestone needs it, and
    ``st.data_editor`` round-trips a list of dicts perfectly well.
    """
    return [
        {
            t("ui.team.col_id"): record.get("id"),
            t("ui.team.col_name"): record.get("name"),
            t("ui.team.col_role"): _LABEL_OF_ROLE.get(str(record.get("role")), record.get("role")),
            t("ui.team.col_pole_position"): bool(record.get("is_pole_position")),
            t("ui.team.col_coaching"): bool(record.get("needs_coaching")),
        }
        for record in records
    ]


def _records(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The editor's rows back as field-named records.

    The shape ``common.roster_records`` has, so an untouched roster compares equal to the team
    and counts as nothing pending.
    """
    return [
        {
            "id": str(row.get(t("ui.team.col_id")) or "").strip(),
            "name": str(row.get(t("ui.team.col_name")) or "").strip(),
            "role": _ROLE_LABELS[label].value
            if (label := str(row.get(t("ui.team.col_role")))) in _ROLE_LABELS
            else None,
            "is_pole_position": bool(row.get(t("ui.team.col_pole_position"))),
            "needs_coaching": bool(row.get(t("ui.team.col_coaching"))),
        }
        for row in rows
    ]


def _to_dancers(records: list[dict[str, Any]]) -> tuple[list[Dancer], list[str]]:
    """Turn pending records into dancers, collecting localized errors instead of raising."""
    dancers: list[Dancer] = []
    errors: list[str] = []
    seen: set[str] = set()

    for number, record in enumerate(records, start=1):
        dancer_id, name = record["id"], record["name"]
        if not dancer_id or not name:
            errors.append(t("ui.team.empty_field", row=number))
            continue
        if dancer_id in seen:
            errors.append(t("ui.team.duplicate_id", dancer_id=dancer_id))
            continue
        seen.add(dancer_id)

        role = Role(record["role"]) if record["role"] in _ROLE_VALUES else Role.LEADER
        pole = bool(record["is_pole_position"])
        coaching = bool(record["needs_coaching"])
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
        desired = [tier for tier in survey.desired_tiers if (tier.dancer_ids & known)]
        not_desired = [tier for tier in survey.not_desired_tiers if (tier.dancer_ids & known)]
        kept.append(
            Survey(
                dancer_id=survey.dancer_id,
                desired_tiers=common.renumber_tiers(desired, known),
                not_desired_tiers=common.renumber_tiers(not_desired, known),
            )
        )
    return kept, len(source.surveys) - len(kept)


def _surviving_constraints(
    rules: list[tuple[str, frozenset[str]]], dancers: list[Dancer]
) -> tuple[CoachConstraints, int]:
    """Drop coach rules that name a dancer who no longer exists.

    A rule is not repaired by shrinking it: "keep these three together" minus one dancer is a
    different rule, and silently keeping the remainder would be a decision the coach never
    made. A group is only kept when every id in it survived.
    """
    known = {dancer.id for dancer in dancers}
    kept: dict[str, list[frozenset[str]]] = {"together": [], "apart": []}
    dropped = 0
    for kind, group in rules:
        if group <= known:
            kept[kind].append(group)
        else:
            dropped += 1
    return CoachConstraints(together=kept["together"], apart=kept["apart"]), dropped


# Mount: feed the editor the pending rows if there are any, else the team -- and keep feeding it
# exactly those rows until it is mounted afresh (navigating away drops the widget key) or the
# language changes (the headings are part of the data).
_language = common.current_language()
_base = st.session_state.get(common.ROSTER_BASE)
if "team_editor" not in st.session_state or not isinstance(_base, tuple) or _base[0] != _language:
    _records_now: list[dict[str, Any]] = (
        list(st.session_state[common.PENDING_ROSTER])
        if common.PENDING_ROSTER in st.session_state
        else common.roster_records(team)
    )
    _base = (_language, _records_now)
    st.session_state[common.ROSTER_BASE] = _base

edited = st.data_editor(
    _rows(_base[1]),
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
st.session_state[common.PENDING_ROSTER] = _records(list(edited))

if "n_positions" not in st.session_state:
    st.session_state["n_positions"] = int(
        st.session_state.get(common.PENDING_N_POSITIONS, team.n_positions)
    )
n_positions = st.number_input(
    t("ui.load.n_positions"), min_value=1, max_value=26, key="n_positions"
)
st.session_state[common.PENDING_N_POSITIONS] = int(n_positions)


# -- coach rules (SPEC.md 8, 7.) -----------------------------------------------------------
#
# Below the roster on purpose: the rules name dancers from the table above, and deleting a
# dancer prunes them in the same apply step. Adding and removing edit the pending list only;
# the Apply button at the bottom is what writes them, together with the roster.

st.subheader(t("ui.team.coach_header"))
st.caption(t("ui.team.coach_help"))
st.caption(t("ui.team.coach_pending"))

# The names the pending rules can use: the roster as it stands in the editor right now, so a
# rule can name a dancer the coach has just added. Rows without an id yet are not nameable.
_NAMES = {
    record["id"]: record["name"] or record["id"]
    for record in st.session_state[common.PENDING_ROSTER]
    if record["id"]
}

if common.PENDING_RULES not in st.session_state:
    st.session_state[common.PENDING_RULES] = common.rules_of(team)
rules: list[tuple[str, frozenset[str]]] = list(st.session_state[common.PENDING_RULES])

if not rules:
    st.caption(t("ui.team.coach_none"))
for index, (kind, group) in enumerate(rules):
    text, button = st.columns([5, 1])
    members = ", ".join(_NAMES.get(i, i) for i in _NAMES if i in group) or ", ".join(sorted(group))
    text.markdown(f"**{_KIND_OF[kind]}** — {members}")
    if button.button(t("ui.team.coach_remove"), key=f"coach_remove_{index}"):
        st.session_state[common.PENDING_RULES] = rules[:index] + rules[index + 1 :]
        st.rerun()

kind_label = st.selectbox(t("ui.team.coach_kind"), options=list(_KIND_LABELS), key="coach_kind")
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
        st.session_state[common.PENDING_RULES] = [*rules, (new_kind, new_group)]
        common.flash("success", t("ui.team.coach_added"))
        st.rerun()


# -- apply ------------------------------------------------------------------------------------

# Everything above has been mirrored into the pending keys by now; let the warnings catch up.
common.refresh_pending_warnings(team)

st.divider()
if common.roster_pending(team):
    st.caption(t("ui.pending.roster"))

if st.button(t("ui.team.apply"), type="primary"):
    dancers, errors = _to_dancers(list(st.session_state[common.PENDING_ROSTER]))
    for error in errors:
        st.error(error)
    if not errors:
        surveys, dropped = _surviving_surveys(team, dancers)
        constraints, dropped_rules = _surviving_constraints(rules, dancers)
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
            for key in (
                common.PENDING_ROSTER,
                common.ROSTER_BASE,
                common.PENDING_N_POSITIONS,
                common.PENDING_RULES,
            ):
                st.session_state.pop(key, None)
            common.prune_pending_surveys({dancer.id for dancer in dancers})
            if dropped:
                common.flash("info", t("ui.team.orphan_survey", n=dropped))
            if dropped_rules:
                common.flash("info", t("ui.team.coach_orphan", n=dropped_rules))
            common.flash("success", t("ui.team.applied", n=len(dancers)))
            st.rerun()
