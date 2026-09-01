"""Command line interface -- the reference interface for the core.

All user-facing output is bilingual (English default, German via DANCEPARTNER_LANG=de) and
goes through :mod:`dancepartner.i18n` (SPEC.md 2). Log records and exception messages stay
English.

Exit codes: ``0`` success, ``1`` the instance or the file was rejected, ``2`` bad invocation
(typer's own), ``3`` the solver returned no solution within its limits.
"""

from __future__ import annotations

import json
import logging
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any

import typer
from pydantic import ValidationError

from .feasibility import FeasibilityIssue, check_feasibility
from .i18n import t
from .model import (
    Direction,
    Objective,
    PreferenceScope,
    Role,
    ScoreAggregation,
    SolverConfig,
    Team,
)
from .reporting import (
    ExchangeGroup,
    exchange_groups,
    group_numbers,
    moved_dancers,
    respected_not_desired,
    satisfaction_ratio,
    satisfaction_rows,
    unfulfilled_desired,
)
from .scoring import DancerSatisfaction, Solution
from .solver import InfeasibleInstanceError, SolveResult, solve
from .storage import MalformedYamlError, StorageError, load_team

__all__ = ["app"]

EXIT_REJECTED = 1
EXIT_NO_SOLUTION = 3

app = typer.Typer(help=t("help.app"), no_args_is_help=True, add_completion=False)

TeamFile = Annotated[Path, typer.Argument(help=t("help.team_file"))]
ResultFile = Annotated[Path, typer.Argument(help=t("help.result_file"))]


# The domain enums use snake_case values because those are what YAML and JSON carry. On the
# command line SPEC.md 11 spells them with hyphens (``--objective maximin-then-sum``), so the
# CLI has its own choice enums and maps by member name.
class ObjectiveChoice(StrEnum):
    """``Objective`` as spelled on the command line."""

    WEIGHTED_SUM = "weighted-sum"
    MAXIMIN_THEN_SUM = "maximin-then-sum"
    LEXIMIN = "leximin"
    LEXICOGRAPHIC_TIERS = "lexicographic-tiers"


class AggregationChoice(StrEnum):
    """``ScoreAggregation`` as spelled on the command line."""

    BEST = "best"
    SUM = "sum"


class ScopeChoice(StrEnum):
    """``PreferenceScope`` as spelled on the command line."""

    CROSS_ROLE_ONLY = "cross-role-only"
    ALL = "all"


# -- shared plumbing ----------------------------------------------------------------------


def _echo(message: str) -> None:
    typer.echo(message)


def _fail(message: str) -> None:
    typer.echo(message, err=True)
    raise typer.Exit(EXIT_REJECTED)


def _read_team(path: Path) -> Team:
    """Load a team, turning every expected failure into a localized message and exit code 1."""
    try:
        return load_team(path)
    except FileNotFoundError:
        _fail(t("error.file_not_found", path=path))
    except MalformedYamlError as error:
        _fail(t("error.invalid_yaml", detail=error))
    except StorageError as error:
        # Valid YAML, wrong shape -- an unknown key, a list where a mapping belongs. Saying
        # "invalid YAML" here would send the coach hunting for a syntax error that is not there.
        _fail(t("error.invalid_shape", detail=error))
    except ValidationError as error:
        details = "\n".join(f"  - {item['msg']}" for item in error.errors())
        _fail(t("error.invalid_team", detail=details))
    raise AssertionError("unreachable")  # pragma: no cover


def _team_summary(team: Team) -> str:
    return t(
        "team.summary",
        n_dancers=len(team.dancers),
        n_leaders=len(team.by_role(Role.LEADER)),
        n_followers=len(team.by_role(Role.FOLLOWER)),
        n_positions=team.n_positions,
        labels=" ".join(team.labels),
    )


def _print_issues(issues: list[FeasibilityIssue]) -> None:
    _echo(t("check.issues", count=len(issues)))
    for issue in issues:
        _echo(t("check.issue", code=issue.code, message=issue.message))
        if issue.involved_ids:
            _echo(t("check.involved", ids=", ".join(issue.involved_ids)))


def _names(team: Team, ids: list[str] | tuple[str, ...]) -> str:
    by_id = team.dancers_by_id
    return ", ".join(by_id[i].name for i in ids) if ids else t("table.nothing")


def _rank_label(rank: int, direction: Direction) -> str:
    """The user-facing name of one preference rank, e.g. "Wish 1" / "No-go 2"."""
    return t(f"tier.{direction}", rank=rank)


def _format_wishes(satisfaction: DancerSatisfaction, team: Team) -> str:
    parts = [
        t("table.fulfilled", label=_rank_label(rank, "desired"), names=_names(team, ids))
        for rank, ids in sorted(satisfaction.fulfilled_desired.items())
    ]
    parts += [
        t("table.violated", label=_rank_label(rank, "not_desired"), names=_names(team, ids))
        for rank, ids in sorted(satisfaction.violated_not_desired.items())
    ]
    return "; ".join(parts) if parts else t("table.nothing")


def _print_scores(solution: Solution, config: SolverConfig) -> None:
    _echo(t("solve.scores", total=solution.total_score, minimum=solution.min_score))
    best_mode = config.aggregation is ScoreAggregation.BEST
    _echo(t("solve.scale_note_best" if best_mode else "solve.scale_note"))


def _print_solution(solution: Solution, team: Team) -> None:
    _echo(t("solve.positions"))
    for position in solution.positions:
        doubled = t("solve.doubled") if position.is_doubled else ""
        _echo(t("solve.position", label=position.label, doubled=doubled))
        _echo(t("solve.leaders", names=_names(team, position.leaders)))
        _echo(t("solve.followers", names=_names(team, position.followers)))


def _print_table(solution: Solution, team: Team) -> None:
    _echo("")
    _echo(t("table.header"))
    _echo(
        t(
            "table.columns",
            name=t("table.col_name"),
            score=t("table.col_score"),
            wishes=t("table.col_wishes"),
        )
    )
    # Ascending -- the unhappiest first, which is the row the coach actually needs.
    for _, name, satisfaction in satisfaction_rows(solution, team):
        _echo(
            t(
                "table.columns",
                name=name,
                score=satisfaction.score,
                wishes=_format_wishes(satisfaction, team),
            )
        )


# -- commands -----------------------------------------------------------------------------


@app.command(help=t("help.check"))
def check(path: TeamFile) -> None:
    """Report the counting obstructions in a team file."""
    team = _read_team(path)
    _echo(_team_summary(team))
    _echo(t("team.surveys", n_surveys=len(team.surveys), n_dancers=len(team.dancers)))
    _echo("")
    issues = check_feasibility(team)
    if not issues:
        _echo(t("check.ok"))
        _echo(t("check.caveat"))
        return
    _print_issues(issues)
    raise typer.Exit(EXIT_REJECTED)


@app.command(help=t("help.solve"))
def solve_command(  # noqa: PLR0913 -- one option per SolverConfig field, by design
    path: TeamFile,
    objective: Annotated[
        ObjectiveChoice, typer.Option("--objective", help=t("help.objective"))
    ] = ObjectiveChoice.LEXIMIN,
    aggregation: Annotated[
        AggregationChoice, typer.Option("--aggregation", help=t("help.aggregation"))
    ] = AggregationChoice.BEST,
    scope: Annotated[ScopeChoice, typer.Option("--scope", help=t("help.scope"))] = ScopeChoice.ALL,
    veto_tier: Annotated[int, typer.Option("--veto-tier", help=t("help.veto_tier"))] = 1,
    top: Annotated[int, typer.Option("--top", min=1, help=t("help.top"))] = 1,
    near_optimal: Annotated[
        float,
        typer.Option("--near-optimal", min=0.01, max=1.0, help=t("help.near_optimal")),
    ] = 1.0,
    tier_slack: Annotated[int, typer.Option("--tier-slack", min=0, help=t("help.tier_slack"))] = 0,
    time_limit: Annotated[
        float, typer.Option("--time-limit", min=0.001, help=t("help.time_limit"))
    ] = 30.0,
    seed: Annotated[int, typer.Option("--seed", help=t("help.seed"))] = 0,
    normalize: Annotated[
        bool, typer.Option("--normalize/--no-normalize", help=t("help.normalize"))
    ] = True,
    prefer_coupled: Annotated[
        bool,
        typer.Option("--prefer-coupled/--no-prefer-coupled", help=t("help.prefer_coupled")),
    ] = True,
    workers: Annotated[int, typer.Option("--workers", min=1, help=t("help.workers"))] = 1,
    json_out: Annotated[Path | None, typer.Option("--json", help=t("help.json"))] = None,
    verbose: Annotated[bool, typer.Option("--verbose", help=t("help.verbose"))] = False,
) -> None:
    """Solve and print the best assignment."""
    if verbose:
        logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    team = _read_team(path)
    config = SolverConfig(
        objective=Objective[objective.name],
        aggregation=ScoreAggregation[aggregation.name],
        scope=PreferenceScope[scope.name],
        # 0 is the CLI's spelling of "no hard vetoes"; SolverConfig rejects it as an int.
        veto_tier=veto_tier if veto_tier > 0 else None,
        normalize_double=normalize,
        prefer_coupled=prefer_coupled,
        tier_slack=tier_slack,
        max_solutions=top,
        near_optimal_ratio=near_optimal,
        max_time_in_seconds=time_limit,
        random_seed=seed,
        num_workers=workers,
        log_search_progress=verbose,
    )

    _echo(_team_summary(team))
    _echo(t("solve.running"))
    try:
        result = solve(team, config)
    except InfeasibleInstanceError as error:
        _echo(t("solve.infeasible_precheck"))
        _print_issues(error.issues)
        raise typer.Exit(EXIT_REJECTED) from None

    _echo("")
    _echo(
        t(
            "solve.status",
            status=result.status,
            wall_time=result.wall_time,
            branches=result.num_branches,
        )
    )
    if not result.solutions:
        _echo(t("solve.no_solution", status=result.status))
        raise typer.Exit(EXIT_NO_SOLUTION)

    _print_stages(result)
    _echo("")
    _print_shortlist(result, team, config)
    _print_table(result.best, team)

    if json_out is not None:
        _write_result(result, config, json_out)
        _echo("")
        _echo(t("solve.written", path=json_out))


def _write_result(result: SolveResult, config: SolverConfig, path: Path) -> None:
    """Write the machine-readable result that ``explain`` reads back."""
    payload = {
        "config": config.model_dump(mode="json"),
        "result": result.model_dump(mode="json"),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


@app.command(help=t("help.explain"))
def explain(
    path: TeamFile,
    result_path: ResultFile,
    dancer: Annotated[str | None, typer.Option("--dancer", help=t("help.dancer"))] = None,
    solution_index: Annotated[int, typer.Option("--solution", min=1, help=t("help.solution"))] = 1,
) -> None:
    """Explain what one dancer -- or everyone -- got out of a stored solution."""
    team = _read_team(path)
    result, config = _read_result(result_path)
    count = len(result.solutions)
    if solution_index > count:
        _fail(t("explain.unknown_solution", count=count, index=solution_index))
    solution = result.solutions[solution_index - 1]

    if count > 1:
        _echo(t("explain.solution_note", index=solution_index, count=count))
        _echo("")

    if dancer is None:
        _print_scores(solution, config)
        _echo("")
        _print_solution(solution, team)
        _print_table(solution, team)
        return
    if dancer not in team.dancers_by_id:
        _fail(t("explain.unknown_dancer", dancer_id=dancer))
    _explain_dancer(dancer, solution, team, config)
    groups = exchange_groups(solution, team, config)
    numbers = group_numbers(groups)
    if dancer in numbers:
        group = groups[numbers[dancer] - 1]
        _echo(t("explain.group", number=group.number, names=_group_members(group, team)))
    if count > 1:
        _echo("")
        _print_across_solutions(dancer, result, team)


def _read_result(path: Path) -> tuple[SolveResult, SolverConfig]:
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        _fail(t("error.file_not_found", path=path))
    except json.JSONDecodeError as error:
        _fail(t("error.invalid_json", detail=error))
    try:
        result = SolveResult.model_validate(raw["result"])
        config = SolverConfig.model_validate(raw["config"])
        if not result.solutions:
            raise ValueError("the result file holds no solution")
        return result, config
    except (KeyError, TypeError, ValidationError, ValueError) as error:
        _fail(t("error.invalid_team", detail=f"  - {error}"))
    raise AssertionError("unreachable")  # pragma: no cover


def _print_across_solutions(dancer_id: str, result: SolveResult, team: Team) -> None:
    """How stable this dancer's partners are across the whole shortlist.

    This is the question the enumeration exists to answer: a partner who appears in every
    near-optimal solution is not a choice the coach has to make, and one that appears in three
    of twenty is.
    """
    by_id = team.dancers_by_id
    count = len(result.solutions)
    hits: dict[str, int] = {}
    for solution in result.solutions:
        position = next(p for p in solution.positions if dancer_id in (*p.leaders, *p.followers))
        for other in (*position.leaders, *position.followers):
            if other != dancer_id:
                hits[other] = hits.get(other, 0) + 1

    if all(value == count for value in hits.values()):
        _echo(t("explain.across_stable", count=count))
        return
    _echo(t("explain.across_header", count=count))
    ordered = sorted(hits.items(), key=lambda item: (-item[1], by_id[item[0]].name))
    for other, value in ordered:
        _echo(t("explain.across_entry", name=by_id[other].name, hits=value, count=count))


def _explain_dancer(dancer_id: str, solution: Solution, team: Team, config: SolverConfig) -> None:
    dancer = team.dancers_by_id[dancer_id]
    position = next(p for p in solution.positions if dancer_id in (*p.leaders, *p.followers))
    satisfaction = solution.per_dancer[dancer_id]
    same_role = [i for i in position.role_ids(dancer.role) if i != dancer_id]
    partners = [i for i in (*position.leaders, *position.followers) if i != dancer_id]

    _echo(
        t(
            "explain.heading",
            name=dancer.name,
            role=t(f"role.{dancer.role.value}"),
            label=position.label,
        )
    )
    _echo(t("explain.score", score=satisfaction.score))
    if config.aggregation is ScoreAggregation.BEST:
        ratio = satisfaction_ratio(team, config, dancer_id, satisfaction)
        if ratio is not None:
            _echo(t("explain.satisfaction", percent=round(ratio * 100)))
    _echo(t("explain.partners", names=_names(team, partners)))
    if dancer.is_pole_position:
        _echo(t("explain.pole_position"))
    if dancer.needs_coaching:
        _echo(t("explain.needs_coaching", names=_names(team, same_role)))

    survey = team.surveys_by_id.get(dancer_id)
    if survey is None:
        _echo(t("explain.no_survey"))
        return

    if satisfaction.fulfilled_desired:
        _echo(t("explain.fulfilled"))
        for rank, ids in sorted(satisfaction.fulfilled_desired.items()):
            _echo(t("explain.entry", label=_rank_label(rank, "desired"), names=_names(team, ids)))
    else:
        _echo(t("explain.no_wishes"))

    missed = unfulfilled_desired(team, dancer_id, satisfaction)
    if missed:
        _echo(t("explain.unfulfilled"))
        for rank, ids in sorted(missed.items()):
            _echo(t("explain.entry", label=_rank_label(rank, "desired"), names=_names(team, ids)))

    if satisfaction.violated_not_desired:
        _echo(t("explain.violated"))
        for rank, ids in sorted(satisfaction.violated_not_desired.items()):
            label = _rank_label(rank, "not_desired")
            _echo(t("explain.entry", label=label, names=_names(team, ids)))

    respected = respected_not_desired(team, config, dancer_id, satisfaction)
    if respected:
        _echo(t("explain.respected"))
        for rank, ids in sorted(respected.items()):
            label = _rank_label(rank, "not_desired")
            _echo(t("explain.entry", label=label, names=_names(team, ids)))

    if satisfaction.neutral_partners:
        _echo(t("explain.neutral", names=_names(team, satisfaction.neutral_partners)))


# typer derives the command name from the function name; "solve" collides with the imported
# solver entry point, so the function is named solve_command and renamed here.
app.registered_commands[1].name = "solve"


def _print_stages(result: SolveResult) -> None:
    _echo(t("solve.stages"))
    for stage in result.stages:
        sense = t(f"solve.sense.{stage.sense.value}")
        if stage.locked_at is None or stage.locked_at == stage.value:
            _echo(t("solve.stage", name=stage.name, value=stage.value, sense=sense))
        else:
            # A later stage spent this one's tier slack; showing only the optimum would
            # overstate what the coach is guaranteed.
            _echo(
                t(
                    "solve.stage_locked",
                    name=stage.name,
                    value=stage.value,
                    sense=sense,
                    locked=stage.locked_at,
                )
            )


def _print_shortlist(result: SolveResult, team: Team, config: SolverConfig) -> None:
    """Print the whole shortlist, each alternative diffed against the best solution."""
    count = len(result.solutions)
    key = "solve.solution_count_truncated" if result.truncated else "solve.solution_count"
    _echo(t(key, count=count))
    if config.near_optimal_ratio < 1.0:
        _echo(t("solve.near_optimal", percent=config.near_optimal_ratio * 100))
    groups = exchange_groups(result.best, team, config)
    if groups:
        _print_groups(groups, team)
    _echo("")

    if count == 1:
        _print_scores(result.best, config)
        _echo("")
        _print_solution(result.best, team)
        return

    for index, solution in enumerate(result.solutions, start=1):
        marker = t("solve.solution_best") if index == 1 else ""
        _echo(t("solve.solution_heading", index=index, count=count, marker=marker))
        _echo(
            t(
                "solve.solution_scores",
                total=solution.total_score,
                minimum=solution.min_score,
            )
        )
        _print_solution(solution, team)
        if index > 1:
            _print_diff(result.best, solution, team)
        _echo("")


def _group_members(group: ExchangeGroup, team: Team) -> str:
    """``"Anna (A), Berta (B)"`` -- the group's dancers with their current positions."""
    by_id = team.dancers_by_id
    return ", ".join(
        t("solve.group_member", name=by_id[i].name, label=group.labels[i])
        for i in sorted(group.dancer_ids, key=lambda i: by_id[i].name)
    )


def _print_groups(groups: list[ExchangeGroup], team: Team) -> None:
    """Print every freely interchangeable dancer set of the best solution.

    This is the answer to "whom can I swap through without making the team unhappier":
    any rearrangement within one group keeps every hard constraint and the score vector
    (see ``reporting.exchange_groups``).
    """
    _echo(t("solve.groups_header"))
    for group in groups:
        role = t(f"role.{group.role.value}.plural")
        _echo(
            t(
                "solve.group_heading",
                number=group.number,
                role=role,
                names=_group_members(group, team),
            )
        )


def _print_diff(reference: Solution, solution: Solution, team: Team) -> None:
    """Show which dancers sit somewhere else than in the reference solution."""
    # `moved` is never empty: the shortlist is deduplicated by signature, so two entries always
    # differ in who sits with whom, not merely in which label a group carries.
    moved = moved_dancers(reference, solution, team)
    _echo(t("solve.diff_header"))
    for name, from_label, to_label in moved:
        _echo(t("solve.diff_entry", name=name, from_label=from_label, to_label=to_label))
