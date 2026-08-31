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
from dancepartner.model import ScoreAggregation
from dancepartner.reporting import (
    exchange_groups,
    group_numbers,
    moved_dancers,
    positions_by_dancer,
    respected_not_desired,
    satisfaction_ratio,
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
best_mode = config.aggregation is ScoreAggregation.BEST
st.caption(t("solve.scale_note_best" if best_mode else "solve.scale_note"))

# -- the satisfaction table ----------------------------------------------------------------

st.subheader(t("ui.analysis.header"))
st.caption(t("ui.analysis.hint"))

rows = satisfaction_rows(selected, team)
scores = [sat.score for _, _, sat in rows]
worst, best_score = min(scores), max(scores)
places = positions_by_dancer(selected)
# A property of the selected solution: any rearrangement within a group is equally good.
groups = exchange_groups(selected, team, config)
numbers = group_numbers(groups)


def _percent(ratio: float | None) -> int | None:
    """Clamp a satisfaction ratio into a 0-100 progress value; ``None`` stays blank."""
    return None if ratio is None else max(min(round(ratio * 100), 100), 0)


if best_mode:
    # The scale is absolute: 100 % is "top wish fulfilled, nothing violated" for everyone.
    ratios = {
        dancer_id: satisfaction_ratio(team, config, dancer_id, sat) for dancer_id, _, sat in rows
    }
    table_rows = [
        {
            "": common.ratio_badge(ratios[dancer_id]),
            t("table.col_name"): name,
            t("ui.analysis.col_position"): places[dancer_id],
            t("ui.analysis.col_group"): (
                common.group_marker(numbers[dancer_id]) if dancer_id in numbers else ""
            ),
            t("ui.analysis.col_satisfaction"): _percent(ratios[dancer_id]),
            t("table.col_score"): sat.score,
            t("ui.analysis.col_fulfilled"): common.tier_summary(team, sat.fulfilled_desired),
            t("ui.analysis.col_violated"): common.tier_summary(team, sat.violated_not_desired),
        }
        for dancer_id, name, sat in rows
    ]
    column_config = {
        t("ui.analysis.col_satisfaction"): st.column_config.ProgressColumn(
            t("ui.analysis.col_satisfaction"),
            min_value=0,
            max_value=100,
            format="%d%%",
        )
    }
else:
    table_rows = [
        {
            "": common.score_badge(sat.score, worst, best_score),
            t("table.col_name"): name,
            t("ui.analysis.col_position"): places[dancer_id],
            t("ui.analysis.col_group"): (
                common.group_marker(numbers[dancer_id]) if dancer_id in numbers else ""
            ),
            t("table.col_score"): sat.score,
            t("ui.analysis.col_fulfilled"): common.tier_summary(team, sat.fulfilled_desired),
            t("ui.analysis.col_violated"): common.tier_summary(team, sat.violated_not_desired),
        }
        for dancer_id, name, sat in rows
    ]
    column_config = {
        t("table.col_score"): st.column_config.ProgressColumn(
            t("table.col_score"),
            min_value=min(worst, 0),
            max_value=max(best_score, 1),
            format="%d",
        )
    }

st.dataframe(
    table_rows,
    hide_index=True,
    use_container_width=True,
    column_config=column_config,
)

# -- the exchange groups -------------------------------------------------------------------
#
# The question the coach asks the diagram: whom can I swap through without making the team
# unhappier? Any rearrangement within one group keeps every hard constraint and the score
# vector of the solution shown. Rendered as markdown, never as a dataframe -- the tests
# address the satisfaction and diff tables by dataframe index.

st.subheader(t("ui.analysis.groups_header"))
if not groups:
    st.caption(t("ui.analysis.groups_none"))
by_id = team.dancers_by_id
for group in groups:
    members = ", ".join(
        t("solve.group_member", name=by_id[i].name, label=group.labels[i])
        for i in sorted(group.dancer_ids, key=lambda i: by_id[i].name)
    )
    role = common.role_plural(group.role)
    st.markdown(f"{common.group_marker(group.number)} {role} — **{members}**")

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

if picked in numbers:
    picked_group = groups[numbers[picked] - 1]
    picked_members = ", ".join(
        t("solve.group_member", name=by_id[i].name, label=picked_group.labels[i])
        for i in sorted(picked_group.dancer_ids, key=lambda i: by_id[i].name)
    )
    st.markdown(t("explain.group", number=picked_group.number, names=picked_members).strip())

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
