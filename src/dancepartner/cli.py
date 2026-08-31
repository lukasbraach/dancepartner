"""Command line interface -- the reference interface for the core.

All user-facing output is German and goes through :mod:`dancepartner.i18n` (SPEC.md 2). Log
records and exception messages stay English.

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
from .i18n import de
from .model import Objective, PreferenceScope, Role, SolverConfig, Team, WeightScheme
from .scoring import DancerSatisfaction, Solution
from .solver import InfeasibleInstanceError, SolveResult, solve
from .storage import MalformedYamlError, StorageError, load_team

__all__ = ["app"]

EXIT_REJECTED = 1
EXIT_NO_SOLUTION = 3

app = typer.Typer(help=de("help.app"), no_args_is_help=True, add_completion=False)

TeamFile = Annotated[Path, typer.Argument(help=de("help.team_file"))]
ResultFile = Annotated[Path, typer.Argument(help=de("help.result_file"))]


# The domain enums use snake_case values because those are what YAML and JSON carry. On the
# command line SPEC.md 11 spells them with hyphens (``--objective maximin-then-sum``), so the
# CLI has its own choice enums and maps by member name.
class ObjectiveChoice(StrEnum):
    """``Objective`` as spelled on the command line."""

    WEIGHTED_SUM = "weighted-sum"
    MAXIMIN_THEN_SUM = "maximin-then-sum"
    LEXIMIN = "leximin"
    LEXICOGRAPHIC_TIERS = "lexicographic-tiers"


class WeightChoice(StrEnum):
    """``WeightScheme`` as spelled on the command line."""

    LINEAR = "linear"
    GEOMETRIC = "geometric"


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
    """Load a team, turning every expected failure into a German message and exit code 1."""
    try:
        return load_team(path)
    except FileNotFoundError:
        _fail(de("error.file_not_found", path=path))
    except MalformedYamlError as error:
        _fail(de("error.invalid_yaml", detail=error))
    except StorageError as error:
        # Valid YAML, wrong shape -- an unknown key, a list where a mapping belongs. Saying
        # "invalid YAML" here would send the coach hunting for a syntax error that is not there.
        _fail(de("error.invalid_shape", detail=error))
    except ValidationError as error:
        details = "\n".join(f"  - {item['msg']}" for item in error.errors())
        _fail(de("error.invalid_team", detail=details))
    raise AssertionError("unreachable")  # pragma: no cover


def _team_summary(team: Team) -> str:
    return de(
        "team.summary",
        n_dancers=len(team.dancers),
        n_leaders=len(team.by_role(Role.LEADER)),
        n_followers=len(team.by_role(Role.FOLLOWER)),
        n_positions=team.n_positions,
        labels=" ".join(team.labels),
    )


def _print_issues(issues: list[FeasibilityIssue]) -> None:
    _echo(de("check.issues", count=len(issues)))
    for issue in issues:
        _echo(de("check.issue", code=issue.code, message=issue.message_de))
        if issue.involved_ids:
            _echo(de("check.involved", ids=", ".join(issue.involved_ids)))


def _names(team: Team, ids: list[str] | tuple[str, ...]) -> str:
    by_id = team.dancers_by_id
    return ", ".join(by_id[i].name for i in ids) if ids else de("table.nothing")


def _format_wishes(satisfaction: DancerSatisfaction, team: Team) -> str:
    parts = [
        de("table.fulfilled", rank=rank, names=_names(team, ids))
        for rank, ids in sorted(satisfaction.fulfilled_desired.items())
    ]
    parts += [
        de("table.violated", rank=rank, names=_names(team, ids))
        for rank, ids in sorted(satisfaction.violated_not_desired.items())
    ]
    return "; ".join(parts) if parts else de("table.nothing")


def _print_scores(solution: Solution) -> None:
    _echo(de("solve.scores", total=solution.total_score, minimum=solution.min_score))
    _echo(de("solve.scale_note"))


def _print_solution(solution: Solution, team: Team) -> None:
    _echo(de("solve.positions"))
    for position in solution.positions:
        doubled = de("solve.doubled") if position.is_doubled else ""
        _echo(de("solve.position", label=position.label, doubled=doubled))
        _echo(de("solve.leaders", names=_names(team, position.leaders)))
        _echo(de("solve.followers", names=_names(team, position.followers)))


def _print_table(solution: Solution, team: Team) -> None:
    _echo("")
    _echo(de("table.header"))
    _echo(
        de(
            "table.columns",
            name=de("table.col_name"),
            score=de("table.col_score"),
            wishes=de("table.col_wishes"),
        )
    )
    by_id = team.dancers_by_id
    # Ascending: the unhappiest first, which is the row the coach actually needs.
    ordered = sorted(solution.per_dancer.items(), key=lambda item: (item[1].score, item[0]))
    for dancer_id, satisfaction in ordered:
        _echo(
            de(
                "table.columns",
                name=by_id[dancer_id].name,
                score=satisfaction.score,
                wishes=_format_wishes(satisfaction, team),
            )
        )


# -- commands -----------------------------------------------------------------------------


@app.command(help=de("help.check"))
def check(path: TeamFile) -> None:
    """Report the counting obstructions in a team file."""
    team = _read_team(path)
    _echo(_team_summary(team))
    _echo(de("team.surveys", n_surveys=len(team.surveys), n_dancers=len(team.dancers)))
    _echo("")
    issues = check_feasibility(team)
    if not issues:
        _echo(de("check.ok"))
        _echo(de("check.caveat"))
        return
    _print_issues(issues)
    raise typer.Exit(EXIT_REJECTED)


@app.command(help=de("help.solve"))
def solve_command(  # noqa: PLR0913 -- one option per SolverConfig field, by design
    path: TeamFile,
    objective: Annotated[
        ObjectiveChoice, typer.Option("--objective", help=de("help.objective"))
    ] = ObjectiveChoice.MAXIMIN_THEN_SUM,
    weights: Annotated[
        WeightChoice, typer.Option("--weights", help=de("help.weights"))
    ] = WeightChoice.LINEAR,
    scope: Annotated[
        ScopeChoice, typer.Option("--scope", help=de("help.scope"))
    ] = ScopeChoice.CROSS_ROLE_ONLY,
    veto_tier: Annotated[int, typer.Option("--veto-tier", help=de("help.veto_tier"))] = 1,
    top: Annotated[int, typer.Option("--top", min=1, help=de("help.top"))] = 1,
    near_optimal: Annotated[
        float,
        typer.Option("--near-optimal", min=0.01, max=1.0, help=de("help.near_optimal")),
    ] = 1.0,
    tier_slack: Annotated[int, typer.Option("--tier-slack", min=0, help=de("help.tier_slack"))] = 0,
    time_limit: Annotated[
        float, typer.Option("--time-limit", min=0.001, help=de("help.time_limit"))
    ] = 30.0,
    seed: Annotated[int, typer.Option("--seed", help=de("help.seed"))] = 0,
    normalize: Annotated[
        bool, typer.Option("--normalize/--no-normalize", help=de("help.normalize"))
    ] = True,
    prefer_coupled: Annotated[
        bool,
        typer.Option("--prefer-coupled/--no-prefer-coupled", help=de("help.prefer_coupled")),
    ] = True,
    workers: Annotated[int, typer.Option("--workers", min=1, help=de("help.workers"))] = 1,
    json_out: Annotated[Path | None, typer.Option("--json", help=de("help.json"))] = None,
    verbose: Annotated[bool, typer.Option("--verbose", help=de("help.verbose"))] = False,
) -> None:
    """Solve and print the best assignment."""
    if verbose:
        logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    team = _read_team(path)
    config = SolverConfig(
        objective=Objective[objective.name],
        weights=WeightScheme[weights.name],
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
    _echo(de("solve.running"))
    try:
        result = solve(team, config)
    except InfeasibleInstanceError as error:
        _echo(de("solve.infeasible_precheck"))
        _print_issues(error.issues)
        raise typer.Exit(EXIT_REJECTED) from None

    _echo("")
    _echo(
        de(
            "solve.status",
            status=result.status,
            wall_time=result.wall_time,
            branches=result.num_branches,
        )
    )
    if not result.solutions:
        _echo(de("solve.no_solution", status=result.status))
        raise typer.Exit(EXIT_NO_SOLUTION)

    _print_stages(result)
    _echo("")
    _print_shortlist(result, team, config)
    _print_table(result.best, team)

    if json_out is not None:
        _write_result(result, config, json_out)
        _echo("")
        _echo(de("solve.written", path=json_out))


def _write_result(result: SolveResult, config: SolverConfig, path: Path) -> None:
    """Write the machine-readable result that ``explain`` reads back."""
    payload = {
        "config": config.model_dump(mode="json"),
        "result": result.model_dump(mode="json"),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


@app.command(help=de("help.explain"))
def explain(
    path: TeamFile,
    result_path: ResultFile,
    dancer: Annotated[str | None, typer.Option("--dancer", help=de("help.dancer"))] = None,
    solution_index: Annotated[int, typer.Option("--solution", min=1, help=de("help.solution"))] = 1,
) -> None:
    """Explain what one dancer -- or everyone -- got out of a stored solution."""
    team = _read_team(path)
    result, config = _read_result(result_path)
    count = len(result.solutions)
    if solution_index > count:
        _fail(de("explain.unknown_solution", count=count, index=solution_index))
    solution = result.solutions[solution_index - 1]

    if count > 1:
        _echo(de("explain.solution_note", index=solution_index, count=count))
        _echo("")

    if dancer is None:
        _print_scores(solution)
        _echo("")
        _print_solution(solution, team)
        _print_table(solution, team)
        return
    if dancer not in team.dancers_by_id:
        _fail(de("explain.unknown_dancer", dancer_id=dancer))
    _explain_dancer(dancer, solution, team, config)
    if count > 1:
        _echo("")
        _print_across_solutions(dancer, result, team)


def _read_result(path: Path) -> tuple[SolveResult, SolverConfig]:
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        _fail(de("error.file_not_found", path=path))
    except json.JSONDecodeError as error:
        _fail(de("error.invalid_json", detail=error))
    try:
        result = SolveResult.model_validate(raw["result"])
        config = SolverConfig.model_validate(raw["config"])
        if not result.solutions:
            raise ValueError("the result file holds no solution")
        return result, config
    except (KeyError, TypeError, ValidationError, ValueError) as error:
        _fail(de("error.invalid_team", detail=f"  - {error}"))
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
        _echo(de("explain.across_stable", count=count))
        return
    _echo(de("explain.across_header", count=count))
    ordered = sorted(hits.items(), key=lambda item: (-item[1], by_id[item[0]].name))
    for other, value in ordered:
        _echo(de("explain.across_entry", name=by_id[other].name, hits=value, count=count))


def _explain_dancer(dancer_id: str, solution: Solution, team: Team, config: SolverConfig) -> None:
    dancer = team.dancers_by_id[dancer_id]
    position = next(p for p in solution.positions if dancer_id in (*p.leaders, *p.followers))
    satisfaction = solution.per_dancer[dancer_id]
    same_role = [i for i in position.role_ids(dancer.role) if i != dancer_id]
    partners = [i for i in (*position.leaders, *position.followers) if i != dancer_id]

    _echo(
        de(
            "explain.heading",
            name=dancer.name,
            role=de(f"role.{dancer.role.value}"),
            label=position.label,
        )
    )
    _echo(de("explain.score", score=satisfaction.score))
    _echo(de("explain.partners", names=_names(team, partners)))
    if dancer.is_pole_position:
        _echo(de("explain.pole_position"))
    if dancer.needs_coaching:
        _echo(de("explain.needs_coaching", names=_names(team, same_role)))

    survey = team.surveys_by_id.get(dancer_id)
    if survey is None:
        _echo(de("explain.no_survey"))
        return

    if satisfaction.fulfilled_desired:
        _echo(de("explain.fulfilled"))
        for rank, ids in sorted(satisfaction.fulfilled_desired.items()):
            _echo(de("explain.entry", rank=rank, names=_names(team, ids)))
    else:
        _echo(de("explain.no_wishes"))

    granted = {i for ids in satisfaction.fulfilled_desired.values() for i in ids}
    missed = {
        tier.rank: sorted(i for i in tier.dancer_ids if i not in granted)
        for tier in survey.desired_tiers
    }
    missed = {rank: ids for rank, ids in missed.items() if ids}
    if missed:
        _echo(de("explain.unfulfilled"))
        for rank, ids in sorted(missed.items()):
            _echo(de("explain.entry", rank=rank, names=_names(team, ids)))

    if satisfaction.violated_not_desired:
        _echo(de("explain.violated"))
        for rank, ids in sorted(satisfaction.violated_not_desired.items()):
            _echo(de("explain.entry", rank=rank, names=_names(team, ids)))

    violated = {i for ids in satisfaction.violated_not_desired.values() for i in ids}
    respected = {
        tier.rank: sorted(
            i
            for i in tier.dancer_ids
            if i not in violated and team.in_scope(dancer_id, i, config.scope)
        )
        for tier in survey.not_desired_tiers
    }
    respected = {rank: ids for rank, ids in respected.items() if ids}
    if respected:
        _echo(de("explain.respected"))
        for rank, ids in sorted(respected.items()):
            _echo(de("explain.entry", rank=rank, names=_names(team, ids)))

    if satisfaction.neutral_partners:
        _echo(de("explain.neutral", names=_names(team, satisfaction.neutral_partners)))


# typer derives the command name from the function name; "solve" collides with the imported
# solver entry point, so the function is named solve_command and renamed here.
app.registered_commands[1].name = "solve"


def _print_stages(result: SolveResult) -> None:
    _echo(de("solve.stages"))
    for stage in result.stages:
        sense = de(f"solve.sense.{stage.sense.value}")
        if stage.locked_at is None or stage.locked_at == stage.value:
            _echo(de("solve.stage", name=stage.name, value=stage.value, sense=sense))
        else:
            # A later stage spent this one's tier slack; showing only the optimum would
            # overstate what the coach is guaranteed.
            _echo(
                de(
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
    _echo(de(key, count=count))
    if config.near_optimal_ratio < 1.0:
        _echo(de("solve.near_optimal", percent=config.near_optimal_ratio * 100))
    _echo("")

    if count == 1:
        _print_scores(result.best)
        _echo("")
        _print_solution(result.best, team)
        return

    for index, solution in enumerate(result.solutions, start=1):
        marker = de("solve.solution_best") if index == 1 else ""
        _echo(de("solve.solution_heading", index=index, count=count, marker=marker))
        _echo(
            de(
                "solve.solution_scores",
                total=solution.total_score,
                minimum=solution.min_score,
            )
        )
        _print_solution(solution, team)
        if index > 1:
            _print_diff(result.best, solution, team)
        _echo("")


def _positions_by_dancer(solution: Solution) -> dict[str, str]:
    return {
        dancer_id: position.label
        for position in solution.positions
        for dancer_id in (*position.leaders, *position.followers)
    }


def _print_diff(reference: Solution, solution: Solution, team: Team) -> None:
    """Show which dancers sit somewhere else than in the reference solution."""
    before = _positions_by_dancer(reference)
    after = _positions_by_dancer(solution)
    by_id = team.dancers_by_id
    moved = [
        (by_id[dancer_id].name, before[dancer_id], after[dancer_id])
        for dancer_id in sorted(after, key=lambda i: by_id[i].name)
        if before[dancer_id] != after[dancer_id]
    ]
    # `moved` is never empty: the shortlist is deduplicated by signature, so two entries always
    # differ in who sits with whom, not merely in which label a group carries.
    _echo(de("solve.diff_header"))
    for name, from_label, to_label in moved:
        _echo(de("solve.diff_entry", name=name, from_label=from_label, to_label=to_label))
