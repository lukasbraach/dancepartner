"""Lösung page: configure the objective, run the solver, show the positions as cards.

Card headings come from i18n, and positions are labelled A-H, never 1-8 --
the model treats them as interchangeable and a number invites a ranking that does not exist
(SPEC.md 8, 10).
"""

from __future__ import annotations

import streamlit as st

import common
from dancepartner.i18n import t
from dancepartner.model import (
    Objective,
    PreferenceScope,
    Role,
    ScoreAggregation,
    SolverConfig,
    WeightScheme,
)
from dancepartner.reporting import satisfaction_ratio
from dancepartner.solver import InfeasibleInstanceError

common.page_header("ui.solve.header")
team = common.require_team()
current = common.get_config()

# -- configuration -------------------------------------------------------------------------

left, middle, right = st.columns(3)

with left:
    objective = st.selectbox(
        t("ui.solve.objective"),
        options=list(Objective),
        index=list(Objective).index(current.objective),
        format_func=common.objective_label,
        help=t("help.objective"),
    )
    weights = st.selectbox(
        t("ui.solve.weights"),
        options=list(WeightScheme),
        index=list(WeightScheme).index(current.weights),
        format_func=common.weights_label,
        help=t("help.weights"),
    )
    aggregation = st.selectbox(
        t("ui.solve.aggregation"),
        options=list(ScoreAggregation),
        index=list(ScoreAggregation).index(current.aggregation),
        format_func=common.aggregation_label,
        help=t("help.aggregation"),
    )

with middle:
    scope = st.selectbox(
        t("ui.solve.scope"),
        options=list(PreferenceScope),
        index=list(PreferenceScope).index(current.scope),
        format_func=common.scope_label,
        help=t("help.scope"),
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

with right:
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

with st.expander(t("ui.solve.advanced")):
    near_optimal = st.slider(
        t("ui.solve.near_optimal"),
        min_value=0.5,
        max_value=1.0,
        value=float(current.near_optimal_ratio),
        step=0.01,
        help=t("help.near_optimal"),
    )
    tier_slack = st.number_input(
        t("ui.solve.tier_slack"),
        min_value=0,
        max_value=10,
        value=current.tier_slack,
        help=t("help.tier_slack"),
        disabled=objective is not Objective.LEXICOGRAPHIC_TIERS,
    )
    normalize = st.checkbox(
        t("ui.solve.normalize"), value=current.normalize_double, help=t("help.normalize")
    )
    prefer_coupled = st.checkbox(
        t("ui.solve.prefer_coupled"),
        value=current.prefer_coupled,
        help=t("help.prefer_coupled"),
    )

config = SolverConfig(
    objective=objective,
    weights=weights,
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

# -- run -------------------------------------------------------------------------------------

if st.button(t("ui.solve.run"), type="primary"):
    # The configured time limit is what keeps the UI from hanging (SPEC.md 10).
    with st.spinner(t("solve.running")):
        try:
            common.set_result(common.cached_solve(team, config))
        except InfeasibleInstanceError as exc:
            st.error(t("solve.infeasible_precheck"))
            common.show_issues(list(exc.issues))
            st.stop()

result = common.get_result()
if result is None:
    st.stop()
if not result.solutions:
    st.error(t("solve.no_solution", status=result.status))
    st.stop()

best = result.best

# -- summary ---------------------------------------------------------------------------------

st.divider()
st.caption(
    t(
        "solve.status",
        status=result.status,
        wall_time=result.wall_time,
        branches=result.num_branches,
    )
)
st.markdown(t("solve.scores", total=best.total_score, minimum=best.min_score))
best_mode = config.aggregation is ScoreAggregation.BEST
st.caption(t("solve.scale_note_best" if best_mode else "solve.scale_note"))

if result.truncated:
    st.info(t("solve.solution_count_truncated", count=len(result.solutions)))
else:
    st.info(t("solve.solution_count", count=len(result.solutions)))
if config.near_optimal_ratio < 1.0:
    st.caption(t("solve.near_optimal", percent=config.near_optimal_ratio * 100))

# -- the cards ---------------------------------------------------------------------------------

st.subheader(t("ui.solve.cards_header"))
scores = [sat.score for sat in best.per_dancer.values()]
worst, top_score = min(scores), max(scores)

for row_start in range(0, len(best.positions), 4):
    for column, position in zip(
        st.columns(4), best.positions[row_start : row_start + 4], strict=False
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
                    satisfaction = best.per_dancer[dancer_id]
                    if best_mode:
                        badge = common.ratio_badge(
                            satisfaction_ratio(team, config, dancer_id, satisfaction)
                        )
                    else:
                        badge = common.score_badge(satisfaction.score, worst, top_score)
                    st.markdown(f"{badge} {team.dancers_by_id[dancer_id].name}")
                    detail = common.satisfaction_badges(satisfaction)
                    if detail:
                        st.markdown(detail)

# -- stages ------------------------------------------------------------------------------------

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
