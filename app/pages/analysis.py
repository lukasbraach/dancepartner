"""Analyse page: who is unhappy, and what the alternatives would change.

Two questions, in the order the coach asks them. First: who did worst out of this assignment --
the table ascends, so that row is at the top. Second: is that a choice at all? A partner who
appears in every optimum is not something the coach has to decide; one who appears in three of
twenty is. That second question is the reason enumeration exists.
"""

from __future__ import annotations

import streamlit as st

import common
from dancepartner.i18n import t
from dancepartner.reporting import (
    moved_dancers,
    positions_by_dancer,
    respected_not_desired,
    satisfaction_rows,
    unfulfilled_desired,
)

common.page_header("ui.analysis.header")
team = common.require_team()
result = common.require_result()
config = common.get_config()

solutions = result.solutions
labels = [
    t("solve.solution_heading", index=i + 1, count=len(solutions), marker="").strip()
    for i in range(len(solutions))
]

# -- which solution are we looking at? -----------------------------------------------------

if len(solutions) > 1:
    index = st.selectbox(
        t("ui.analysis.pick"),
        options=range(len(solutions)),
        format_func=lambda i: labels[i] + (t("solve.solution_best") if i == 0 else ""),
    )
else:
    index = 0
selected = solutions[index]

st.markdown(t("solve.solution_scores", total=selected.total_score, minimum=selected.min_score))
st.caption(t("solve.scale_note"))

# -- the satisfaction table ----------------------------------------------------------------

st.subheader(t("ui.analysis.header"))
st.caption(t("ui.analysis.hint"))

rows = satisfaction_rows(selected, team)
scores = [sat.score for _, _, sat in rows]
worst, best_score = min(scores), max(scores)
places = positions_by_dancer(selected)

st.dataframe(
    [
        {
            "": common.score_badge(sat.score, worst, best_score),
            t("table.col_name"): name,
            t("ui.analysis.col_position"): places[dancer_id],
            t("table.col_score"): sat.score,
            t("ui.analysis.col_fulfilled"): common.tier_summary(team, sat.fulfilled_desired),
            t("ui.analysis.col_violated"): common.tier_summary(team, sat.violated_not_desired),
        }
        for dancer_id, name, sat in rows
    ],
    hide_index=True,
    use_container_width=True,
    column_config={
        t("table.col_score"): st.column_config.ProgressColumn(
            t("table.col_score"),
            min_value=min(worst, 0),
            max_value=max(best_score, 1),
            format="%d",
        )
    },
)

# -- the shortlist browser -----------------------------------------------------------------

st.subheader(t("ui.analysis.shortlist_header"))
if result.truncated:
    st.caption(t("solve.solution_count_truncated", count=len(solutions)))
else:
    st.caption(t("solve.solution_count", count=len(solutions)))

if len(solutions) == 1:
    st.info(t("ui.analysis.only_one"))
else:
    compared = st.selectbox(
        t("ui.analysis.diff_header", index=index + 1),
        options=[i for i in range(len(solutions)) if i != index],
        format_func=lambda i: labels[i],
    )
    moved = moved_dancers(selected, solutions[compared], team)
    if not moved:
        st.info(t("ui.analysis.diff_none"))
    else:
        st.dataframe(
            [
                {
                    t("table.col_name"): name,
                    t("ui.analysis.col_from"): from_label,
                    t("ui.analysis.col_to"): to_label,
                }
                for name, from_label, to_label in moved
            ],
            hide_index=True,
            use_container_width=True,
        )

# -- one dancer in detail ------------------------------------------------------------------

st.subheader(t("ui.analysis.detail_header"))
picked = st.selectbox(
    t("ui.survey.pick"),
    options=[dancer_id for dancer_id, _, _ in rows],
    format_func=lambda i: team.dancers_by_id[i].name,
)
dancer = team.dancers_by_id[picked]
satisfaction = selected.per_dancer[picked]
position = next(p for p in selected.positions if picked in (*p.leaders, *p.followers))
partners = [i for i in (*position.leaders, *position.followers) if i != picked]

st.markdown(
    t(
        "explain.heading",
        name=dancer.name,
        role=common.role_label(dancer.role),
        label=position.label,
    )
)
st.markdown(t("explain.score", score=satisfaction.score).strip())
st.markdown(t("explain.partners", names=common.names(team, partners)).strip())

if dancer.is_pole_position:
    st.caption(t("explain.pole_position").strip())
if dancer.needs_coaching:
    same_role = [i for i in position.role_ids(dancer.role) if i != picked]
    st.caption(t("explain.needs_coaching", names=common.names(team, same_role)).strip())

if picked not in team.surveys_by_id:
    st.caption(t("explain.no_survey").strip())
else:
    detail = {
        "explain.fulfilled": satisfaction.fulfilled_desired,
        "explain.unfulfilled": unfulfilled_desired(team, picked, satisfaction),
        "explain.violated": satisfaction.violated_not_desired,
        "explain.respected": respected_not_desired(team, config, picked, satisfaction),
    }
    for heading, tiers in detail.items():
        if tiers:
            st.markdown(f"**{t(heading).strip()}** {common.tier_summary(team, tiers)}")
    if satisfaction.neutral_partners:
        st.caption(
            t("explain.neutral", names=common.names(team, satisfaction.neutral_partners)).strip()
        )

# -- how stable is this dancer's position across the shortlist? ----------------------------

if len(solutions) > 1:
    counts: dict[str, int] = {}
    for solution in solutions:
        here = next(p for p in solution.positions if picked in (*p.leaders, *p.followers))
        for other in (*here.leaders, *here.followers):
            if other != picked:
                counts[other] = counts.get(other, 0) + 1

    if all(hits == len(solutions) for hits in counts.values()) and len(counts) == len(partners):
        st.success(t("explain.across_stable", count=len(solutions)).strip())
    else:
        st.markdown(t("explain.across_header", count=len(solutions)).strip())
        for other, hits in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
            st.caption(
                t(
                    "explain.across_entry",
                    name=team.dancers_by_id[other].name,
                    hits=hits,
                    count=len(solutions),
                ).strip()
            )
