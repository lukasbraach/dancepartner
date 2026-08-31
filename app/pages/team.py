"""Team page: edit the roster in a table.

The column headings the coach reads stay German ("Startanspruch", "Coachingbedarf") like every
other user-facing string; the underlying fields keep their English names (SPEC.md 2, 3).
"""

from __future__ import annotations

from typing import Any

import streamlit as st

import common
from dancepartner.i18n import de
from dancepartner.model import Dancer, Role, Survey, Team

common.page_header("ui.team.header")
team = common.require_team()
st.caption(de("ui.team.hint"))

_ROLE_LABELS = {common.role_label(role): role for role in Role}


def _rows(source: Team) -> list[dict[str, Any]]:
    """The roster as plain dicts.

    Deliberately not a DataFrame: SPEC.md 4 keeps pandas out unless a milestone needs it, and
    ``st.data_editor`` round-trips a list of dicts perfectly well.
    """
    return [
        {
            de("ui.team.col_id"): dancer.id,
            de("ui.team.col_name"): dancer.name,
            de("ui.team.col_role"): common.role_label(dancer.role),
            de("ui.team.col_pole_position"): dancer.is_pole_position,
            de("ui.team.col_coaching"): dancer.needs_coaching,
        }
        for dancer in source.dancers
    ]


def _to_dancers(rows: list[dict[str, Any]]) -> tuple[list[Dancer], list[str]]:
    """Turn edited rows back into dancers, collecting German errors instead of raising."""
    dancers: list[Dancer] = []
    errors: list[str] = []
    seen: set[str] = set()

    for number, row in enumerate(rows, start=1):
        dancer_id = str(row.get(de("ui.team.col_id")) or "").strip()
        name = str(row.get(de("ui.team.col_name")) or "").strip()
        if not dancer_id or not name:
            errors.append(de("ui.team.empty_field", row=number))
            continue
        if dancer_id in seen:
            errors.append(de("ui.team.duplicate_id", dancer_id=dancer_id))
            continue
        seen.add(dancer_id)

        role = _ROLE_LABELS.get(str(row.get(de("ui.team.col_role"))), Role.LEADER)
        pole = bool(row.get(de("ui.team.col_pole_position")))
        coaching = bool(row.get(de("ui.team.col_coaching")))
        if pole and coaching:
            # Report it in German rather than letting pydantic raise in English.
            errors.append(de("ui.team.flags_exclusive", name=name))
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


edited = st.data_editor(
    _rows(team),
    num_rows="dynamic",
    use_container_width=True,
    hide_index=True,
    column_config={
        de("ui.team.col_id"): st.column_config.TextColumn(de("ui.team.col_id"), required=True),
        de("ui.team.col_name"): st.column_config.TextColumn(de("ui.team.col_name"), required=True),
        de("ui.team.col_role"): st.column_config.SelectboxColumn(
            de("ui.team.col_role"), options=list(_ROLE_LABELS), required=True
        ),
        de("ui.team.col_pole_position"): st.column_config.CheckboxColumn(
            de("ui.team.col_pole_position"), help=de("ui.team.help_pole_position")
        ),
        de("ui.team.col_coaching"): st.column_config.CheckboxColumn(
            de("ui.team.col_coaching"), help=de("ui.team.help_coaching")
        ),
    },
    key="team_editor",
)

n_positions = st.number_input(
    de("ui.load.n_positions"), min_value=1, max_value=26, value=team.n_positions
)

if st.button(de("ui.team.apply"), type="primary"):
    dancers, errors = _to_dancers(list(edited))
    for error in errors:
        st.error(error)
    if not errors:
        surveys, dropped = _surviving_surveys(team, dancers)
        try:
            updated = Team(dancers=dancers, surveys=surveys, n_positions=int(n_positions))
        except ValueError as exc:
            st.error(de("error.invalid_team", detail=exc))
        else:
            common.set_team(updated)
            if dropped:
                st.info(de("ui.team.orphan_survey", n=dropped))
            st.success(de("ui.team.applied", n=len(dancers)))
            st.rerun()
