"""Solution page: settings, pre-check, the solve, and everything there is to say about it.

Three questions, in the order the coach asks them. What does "good" mean here -- the settings,
and the pre-check right beside them, because the veto tier and the wish scope change its
verdict. Who ended up where -- the positions as cards, A-H, never 1-8: the model treats them as
interchangeable and a number invites a ranking that does not exist (SPEC.md 8, 10). And who did
worst, and is that a choice at all -- the satisfaction table ascends so that row is on top, and
a partner who appears in every optimum is nothing the coach has to decide, while one who appears
in three of twenty is. That last question is the reason enumeration exists.

One picker, one solution: every tab renders the shortlist entry ``common.SOLUTION_INDEX_KEY``
names, so the cards, the table, the diff and the dancer detail never disagree about which
assignment they describe. ``st.tabs`` renders every tab on every run, so what they share is
computed once, above them.
"""

from __future__ import annotations

import streamlit as st

import common
from dancepartner.i18n import t
from dancepartner.model import (
    Direction,
    Objective,
    PreferenceScope,
    Role,
    ScoreAggregation,
    SolverConfig,
)
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
from dancepartner.results import dump_result_json

common.page_header("ui.solve.header")
team = common.require_team()

# No solver, no page -- a core-only install. Say so rather than failing, and say it before the
# configuration widgets render, otherwise the coach picks settings for a run that cannot happen.
# The page stays in the navigation and explains itself (SPEC.md 14). The browser build is not
# this case: it solves with HiGHS.
if not common.SOLVER_AVAILABLE:
    st.info(t("ui.solver.unavailable"))
    st.stop()
current = common.get_config()

# -- configuration -------------------------------------------------------------------------
#
# The main area holds what changes the answer; the search budget and the fine-tuning knobs
# sit behind "More settings" (SPEC.md 10).

left, middle, right = st.columns(3)

with left:
    objective = st.selectbox(
        t("ui.solve.objective"),
        options=list(Objective),
        index=list(Objective).index(current.objective),
        format_func=common.objective_label,
        help=t("help.objective"),
    )
    # 0 is the UI spelling of "no hard vetoes at all", matching the CLI's --veto-tier 0.
    veto_tier = st.number_input(
        t("ui.solve.veto_tier"),
        min_value=0,
        max_value=max(team.max_rank, 1),
        value=current.veto_tier or 0,
        help=t("help.veto_tier"),
    )

    if veto_tier == 0:
        st.caption(t("ui.solve.veto_none"))

with middle:
    scope = st.selectbox(
        t("ui.solve.scope"),
        options=list(PreferenceScope),
        index=list(PreferenceScope).index(current.scope),
        format_func=common.scope_label,
        help=t("help.scope"),
    )

with right:
    aggregation = st.selectbox(
        t("ui.solve.aggregation"),
        options=list(ScoreAggregation),
        index=list(ScoreAggregation).index(current.aggregation),
        format_func=common.aggregation_label,
        help=t("help.aggregation"),
    )

    normalize = st.checkbox(
        t("ui.solve.normalize"), value=current.normalize_double, help=t("help.normalize")
    )

    prefer_coupled = st.checkbox(
        t("ui.solve.prefer_coupled"),
        value=current.prefer_coupled,
        help=t("help.prefer_coupled"),
    )

with st.expander(t("ui.solve.advanced")):
    near_optimal = st.slider(
        t("ui.solve.near_optimal"),
        min_value=0.5,
        max_value=1.0,
        value=float(current.near_optimal_ratio),
        step=0.01,
        help=t("help.near_optimal"),
    )
    top = st.number_input(
        t("ui.solve.top"),
        min_value=1,
        max_value=200,
        value=current.max_solutions,
        help=t("help.top"),
    )
    time_limit = st.number_input(
        t("ui.solve.time_limit"),
        min_value=1.0,
        max_value=600.0,
        value=float(current.max_time_in_seconds),
        step=1.0,
        help=t("help.time_limit"),
    )
    tier_slack = st.number_input(
        t("ui.solve.tier_slack"),
        min_value=0,
        max_value=10,
        value=current.tier_slack,
        help=t("help.tier_slack"),
        disabled=objective is not Objective.LEXICOGRAPHIC_TIERS,
    )

config = SolverConfig(
    objective=objective,
    aggregation=aggregation,
    scope=scope,
    veto_tier=int(veto_tier) if veto_tier else None,
    max_solutions=int(top),
    max_time_in_seconds=float(time_limit),
    near_optimal_ratio=float(near_optimal),
    tier_slack=int(tier_slack),
    normalize_double=normalize,
    prefer_coupled=prefer_coupled,
)
common.set_config(config)

# -- pre-check -----------------------------------------------------------------------------
#
# Right under the widgets that change its verdict. The button stays enabled: the solver runs
# the same checks and solve_and_store reports them, so there is one failure path, not two.

st.subheader(t("ui.feasibility.header"))
common.render_feasibility(team, config)

# -- run -------------------------------------------------------------------------------------

if st.button(t("ui.solve.run"), type="primary"):
    # Drawn into a placeholder so it can be taken down again the moment there is an answer.
    # What actually gets it on screen before the solver blocks is the yield inside
    # solve_and_store -- see common.flush_ui, and do not reorder these two (SPEC.md 14.7).
    banner = st.empty()
    with banner.container():
        st.info(t("solve.working"), icon="⏳")
        st.caption(t("solve.working_hint", seconds=config.max_time_in_seconds))
    common.solve_and_store(team, config)
    banner.empty()

result = common.get_result()
if result is None:
    st.info(t("ui.no_solution_yet"))
    st.stop()
if not result.solutions:
    st.error(t("solve.no_solution", status=result.status))
    st.stop()

# -- which solution, and the exports -----------------------------------------------------------

st.divider()
st.caption(
    t(
        "solve.status",
        status=result.status,
        wall_time=result.wall_time,
        branches=result.num_branches,
    )
)

solutions = result.solutions
labels = [
    t("solve.solution_heading", index=i + 1, count=len(solutions), marker="").strip()
    for i in range(len(solutions))
]
picker, as_json, as_csv = st.columns([2, 1, 1], vertical_alignment="bottom")
with picker:
    index = st.selectbox(
        t("ui.solve.pick"),
        options=list(range(len(solutions))),
        format_func=lambda i: labels[i] + (t("solve.solution_best") if i == 0 else ""),
        key=common.SOLUTION_INDEX_KEY,
        disabled=len(solutions) == 1,
    )
selected = solutions[index]
with as_json:
    # Exactly the file `solve --json` writes, so `explain` reads it back (SPEC.md 11).
    st.download_button(
        t("ui.export.json"),
        data=dump_result_json(result, config),
        file_name="result.json",
        mime="application/json",
        help=t("ui.export.json_hint"),
        use_container_width=True,
    )
with as_csv:
    st.download_button(
        t("ui.export.csv", index=index + 1),
        data=common.solution_csv(selected, team, config),
        file_name=f"solution-{index + 1}.csv",
        mime="text/csv",
        use_container_width=True,
    )

st.markdown(t("solve.solution_scores", total=selected.total_score, minimum=selected.min_score))
best_mode = config.aggregation is ScoreAggregation.BEST
st.caption(t("solve.scale_note_best" if best_mode else "solve.scale_note"))
if result.truncated:
    st.info(t("solve.solution_count_truncated", count=len(solutions)))
else:
    st.info(t("solve.solution_count", count=len(solutions)))
if config.near_optimal_ratio < 1.0:
    st.caption(t("solve.near_optimal", percent=config.near_optimal_ratio * 100))

# Shared by every tab: computed once, for the selected solution.
rows = satisfaction_rows(selected, team)
scores = [sat.score for _, _, sat in rows]
worst, best_score = min(scores), max(scores)
places = positions_by_dancer(selected)
# A property of the selected solution: any rearrangement within a group is equally good.
groups = exchange_groups(selected, team, config)
numbers = group_numbers(groups)
by_id = team.dancers_by_id
ratios = (
    {dancer_id: satisfaction_ratio(team, config, dancer_id, sat) for dancer_id, _, sat in rows}
    if best_mode
    else {}
)


def _badge(dancer_id: str) -> str:
    """The colour cue for one dancer, on the scale the aggregation calls for (SPEC.md 10)."""
    if best_mode:
        return common.ratio_badge(ratios[dancer_id])
    return common.score_badge(selected.per_dancer[dancer_id].score, worst, best_score)


def _percent(ratio: float | None) -> int | None:
    """Clamp a satisfaction ratio into a 0-100 progress value; ``None`` stays blank."""
    return None if ratio is None else max(min(round(ratio * 100), 100), 0)


def _group_members(group_index: int) -> str:
    group = groups[group_index]
    return ", ".join(
        t("solve.group_member", name=by_id[i].name, label=group.labels[i])
        for i in sorted(group.dancer_ids, key=lambda i: by_id[i].name)
    )


positions_tab, satisfaction_tab, alternatives_tab, dancer_tab = st.tabs(
    [
        t("ui.solve.tab_positions"),
        t("ui.solve.tab_satisfaction"),
        t("ui.solve.tab_alternatives"),
        t("ui.solve.tab_dancer"),
    ]
)

# -- the cards ---------------------------------------------------------------------------------

with positions_tab:
    if groups:
        st.caption(t("ui.solve.groups_hint"))
    for row_start in range(0, len(selected.positions), 4):
        for column, position in zip(
            st.columns(4), selected.positions[row_start : row_start + 4], strict=False
        ):
            with column, st.container(border=True):
                heading = t("solve.position", label=position.label, doubled="").strip()
                st.markdown(f"**{heading}**")
                if position.is_doubled:
                    st.markdown(f":violet-badge[{t('ui.solve.doubled_badge')}]")

                for role, ids in (
                    (Role.LEADER, position.leaders),
                    (Role.FOLLOWER, position.followers),
                ):
                    st.caption(common.role_plural(role))
                    for dancer_id in ids:
                        marker = (
                            common.group_marker(numbers[dancer_id]) if dancer_id in numbers else ""
                        )
                        st.markdown(
                            f"{_badge(dancer_id)} {by_id[dancer_id].name} {marker}".rstrip()
                        )
                        badges = common.satisfaction_badges(selected.per_dancer[dancer_id])
                        if badges:
                            st.markdown(badges)

    # How this result was reached, stage by stage -- it belongs with the answer, not the table.
    with st.expander(t("ui.solve.stages_header")):
        st.dataframe(
            [
                {
                    t("ui.solve.col_stage"): stage.name,
                    t("ui.solve.col_sense"): common.sense_label(stage.sense.value),
                    t("ui.solve.col_value"): stage.value,
                    t("ui.solve.col_locked"): (
                        stage.locked_at if stage.locked_at is not None else stage.value
                    ),
                }
                for stage in result.stages
            ],
            hide_index=True,
            use_container_width=True,
        )

# -- the satisfaction table and the exchange groups -----------------------------------------------

with satisfaction_tab:
    st.caption(t("ui.analysis.hint"))
    table_rows = []
    for dancer_id, name, sat in rows:
        row: dict[str, object] = {
            "": _badge(dancer_id),
            t("table.col_name"): name,
            t("ui.analysis.col_position"): places[dancer_id],
            t("ui.analysis.col_group"): (
                common.group_marker(numbers[dancer_id]) if dancer_id in numbers else ""
            ),
        }
        if best_mode:
            # The scale is absolute: 100 % is "top wish fulfilled, nothing violated" for everyone.
            row[t("ui.analysis.col_satisfaction")] = _percent(ratios[dancer_id])
        row[t("table.col_score")] = sat.score
        row[t("ui.analysis.col_fulfilled")] = common.tier_summary(
            team, sat.fulfilled_desired, "desired"
        )
        row[t("ui.analysis.col_violated")] = common.tier_summary(
            team, sat.violated_not_desired, "not_desired"
        )
        table_rows.append(row)

    if best_mode:
        column_config = {
            t("ui.analysis.col_satisfaction"): st.column_config.ProgressColumn(
                t("ui.analysis.col_satisfaction"), min_value=0, max_value=100, format="%d%%"
            )
        }
    else:
        column_config = {
            t("table.col_score"): st.column_config.ProgressColumn(
                t("table.col_score"),
                min_value=min(worst, 0),
                max_value=max(best_score, 1),
                format="%d",
            )
        }
    st.dataframe(table_rows, hide_index=True, use_container_width=True, column_config=column_config)

    # Whom can I swap through without making the team unhappier? Any rearrangement within one
    # group keeps every hard constraint and the score vector of the solution shown. Markdown,
    # never a dataframe -- the tests address the tables by dataframe index.
    st.subheader(t("ui.analysis.groups_header"))
    if not groups:
        st.caption(t("ui.analysis.groups_none"))
    for group_index, group in enumerate(groups):
        role_name = common.role_plural(group.role)
        st.markdown(
            f"{common.group_marker(group.number)} {role_name} — **{_group_members(group_index)}**"
        )

# -- the shortlist --------------------------------------------------------------------------------

with alternatives_tab:
    if result.truncated:
        st.caption(t("solve.solution_count_truncated", count=len(solutions)))
    else:
        st.caption(t("solve.solution_count", count=len(solutions)))

    if len(solutions) == 1:
        st.info(t("ui.analysis.only_one"))
    else:
        # Unkeyed on purpose: its options depend on the picker above, and a fresh widget per
        # selection is exactly right for a comparison.
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

# -- one dancer in detail ----------------------------------------------------------------------

with dancer_tab:
    picked = st.selectbox(
        t("ui.solve.dancer_pick"),
        options=[dancer_id for dancer_id, _, _ in rows],
        format_func=lambda i: by_id[i].name,
        key="dancer_pick",
    )
    dancer = by_id[picked]
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
        detail: dict[str, tuple[dict[int, list[str]], Direction]] = {
            "explain.fulfilled": (satisfaction.fulfilled_desired, "desired"),
            "explain.unfulfilled": (unfulfilled_desired(team, picked, satisfaction), "desired"),
            "explain.violated": (satisfaction.violated_not_desired, "not_desired"),
            "explain.respected": (
                respected_not_desired(team, config, picked, satisfaction),
                "not_desired",
            ),
        }
        for heading_key, (tiers, direction) in detail.items():
            if tiers:
                summary = common.tier_summary(team, tiers, direction)
                st.markdown(f"**{t(heading_key).strip()}** {summary}")
        if satisfaction.neutral_partners:
            st.caption(
                t(
                    "explain.neutral", names=common.names(team, satisfaction.neutral_partners)
                ).strip()
            )

    # How stable is this dancer's place across the shortlist?
    if picked in numbers:
        st.markdown(
            t(
                "explain.group",
                number=numbers[picked],
                names=_group_members(numbers[picked] - 1),
            ).strip()
        )

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
                        name=by_id[other].name,
                        hits=hits,
                        count=len(solutions),
                    ).strip()
                )
