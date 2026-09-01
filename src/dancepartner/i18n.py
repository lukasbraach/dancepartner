"""User-facing strings for the CLI and the Streamlit UI, in English and German.

SPEC.md 2: all user-facing output is bilingual and routed through this module. Never inline a
user-facing literal in a widget call or a ``print``; add a key to *both* tables instead.
Everything *about* the code -- identifiers, comments, docstrings, log records, exception
messages -- stays English.

Keys are namespaced by surface (``feasibility.``, ``help.``) and the values are ``str.format``
templates. The two tables share one key set and, per key, one placeholder set; the test suite
enforces both. Call :func:`t`.

The active language starts from the ``DANCEPARTNER_LANG`` environment variable (``en``/``de``,
anything else falls back to English) read once at import. The Streamlit app switches it per
rerun via :func:`set_language`. Typer help texts resolve at import time, so only the
environment variable -- never a later :func:`set_language` -- affects ``--help`` output.
"""

from __future__ import annotations

import os
from enum import StrEnum

__all__ = ["ENV_VAR", "TABLES", "Language", "get_language", "set_language", "t"]

ENV_VAR = "DANCEPARTNER_LANG"


class Language(StrEnum):
    """A language the CLI and the UI can speak."""

    EN = "en"
    DE = "de"


_STRINGS_EN: dict[str, str] = {
    # -- feasibility diagnostics (feasibility.FeasibilityIssue.message) -------------------
    "feasibility.ROLE_COUNT_OUT_OF_RANGE": (
        "{role_label}: {n} dancers for {p} positions. Every position needs one or two — "
        "so {p} to {max_n} are possible."
    ),
    "feasibility.TOO_MANY_POLE_POSITION": (
        "{role_label}: {count} with a pole-position claim, but only {available} position(s) "
        "with single occupancy ({n} {role_label} for {p} positions)."
    ),
    "feasibility.TOO_MANY_COACHING": (
        "{role_label}: {count} with a coaching need each require their own doubled position "
        "with an experienced partner, but there are only {available} ({n} {role_label} for "
        "{p} positions)."
    ),
    "feasibility.VETO_ALL_CROSS_ROLE": (
        "{name} lists all {opposite_label} as not-desired partners (veto) — but every "
        "position is staffed with both roles."
    ),
    "feasibility.VETO_COACHING_ISOLATED": (
        "{name} has a coaching need, but none of the other {role_label} is an experienced "
        "partner without a veto — no doubled position is possible."
    ),
    "feasibility.VETO_FORCES_SINGLES": (
        "{role_label}: {count} dancers cannot form a doubled position because of "
        "pole-position claims or vetoes, but there are only {available} position(s) with "
        "single occupancy."
    ),
    # -- roles ---------------------------------------------------------------------------
    "role.leader.plural": "Leaders",
    "role.follower.plural": "Followers",
    "role.leader": "Leader",
    "role.follower": "Follower",
    # -- shared --------------------------------------------------------------------------
    "team.summary": (
        "{n_dancers} dancers ({n_leaders} leaders, {n_followers} followers) "
        "on {n_positions} positions {labels}."
    ),
    "team.surveys": "{n_surveys} of {n_dancers} have answered the team survey.",
    "error.file_not_found": "File not found: {path}",
    "error.invalid_team": "The team file is invalid:\n{detail}",
    "error.invalid_yaml": "The file is not valid YAML: {detail}",
    "error.invalid_shape": "The file does not have the expected structure: {detail}",
    "error.invalid_json": "The result file is not valid JSON: {detail}",
    # -- check ---------------------------------------------------------------------------
    "check.ok": "No countable obstacles found.",
    "check.caveat": (
        "This does not guarantee a solution — it only means that no simple counting "
        "argument rules one out. The solver has the final say."
    ),
    "check.issues": "{count} problem(s) found:",
    "check.issue": "  [{code}] {message}",
    "check.involved": "      involved: {ids}",
    # -- solve ---------------------------------------------------------------------------
    "solve.running": "Searching for an optimal partner assignment …",
    "solve.working": "Searching for an optimal partner assignment …",
    "solve.working_hint": (
        "This can take up to {seconds:.0f} seconds. The page stays busy until it is done."
    ),
    "solve.infeasible_precheck": "The team file is not solvable:",
    "solve.no_solution": "No solution found (status {status}).",
    "solve.status": "Status: {status} — {wall_time:.2f} s, {branches} branches.",
    "solve.stages": "Objective in stages:",
    "solve.stage": "  {name}: {value} ({sense})",
    "solve.stage_locked": "  {name}: {value} ({sense}), locked in: at least {locked}",
    "solve.sense.maximize": "maximized",
    "solve.sense.minimize": "minimized",
    "solve.scores": "Total score: {total}   lowest individual score: {minimum}",
    "solve.scale_note": "Scores are on the solver's ×2 scale (doubled-position normalization).",
    "solve.scale_note_best": (
        "Scores count the best fulfilled wish per dancer, on the solver's ×2 scale; "
        "100 % satisfaction = first wish fulfilled, nothing violated."
    ),
    "solve.positions": "Positions:",
    "solve.position": "  Position {label}{doubled}",
    "solve.doubled": "  (doubled)",
    "solve.leaders": "     Leaders:   {names}",
    "solve.followers": "     Followers: {names}",
    "solve.solution_count": "{count} equally good solution(s) found.",
    "solve.solution_count_truncated": (
        "At least {count} equally good solutions — the list is cut off at {count}. "
        "Request more with --top."
    ),
    "solve.near_optimal": (
        "Near-optimal solutions down to {percent:.0f} % of the optimum are allowed."
    ),
    "solve.solution_heading": "── Solution {index} of {count}{marker}",
    "solve.solution_best": " (best)",
    "solve.solution_scores": "   Total score {total}, lowest individual score {minimum}",
    "solve.diff_header": "   Difference to solution 1:",
    "solve.diff_entry": "     {name}: {from_label} → {to_label}",
    "solve.groups_header": (
        "Exchange groups — freely interchangeable, every arrangement equally good:"
    ),
    "solve.group_heading": "  Group {number} ({role}): {names}",
    "solve.group_member": "{name} ({label})",
    "solve.written": "Result written to {path}.",
    # -- satisfaction table --------------------------------------------------------------
    "table.header": "Satisfaction (least satisfied first):",
    # Ranks are named, never numbered "Tier N": the coach reads wishes, not tiers. Composed
    # into table.* and explain.entry, so the wording lives in exactly one place per language.
    "tier.desired": "Wish {rank}",
    "tier.not_desired": "No-go {rank}",
    "table.columns": "{name:<20} {score:>7}  {wishes}",
    "table.col_name": "Dancer",
    "table.col_score": "Score",
    "table.col_wishes": "Fulfilled / violated",
    "table.fulfilled": "{label}: {names}",
    "table.violated": "{label} violated: {names}",
    "table.nothing": "—",
    # -- explain -------------------------------------------------------------------------
    "explain.unknown_dancer": "Unknown dancer ID: {dancer_id}",
    "explain.unknown_solution": (
        "The result file contains only {count} solution(s); solution {index} does not exist."
    ),
    "explain.solution_note": "(from solution {index} of {count})",
    "explain.across_header": "  Across all {count} solutions:",
    "explain.across_entry": "    {name}: in {hits} of {count} solutions",
    "explain.across_stable": (
        "  This placement is the same in all {count} solutions — there is nothing to choose here."
    ),
    "explain.group": (
        "  Exchange group {number}: {names} — freely interchangeable, every arrangement "
        "equally good."
    ),
    "explain.heading": "{name} ({role}) — Position {label}",
    "explain.score": "  Score: {score}",
    "explain.satisfaction": "  Satisfaction: {percent} %",
    "explain.partners": "  On the same position: {names}",
    "explain.fulfilled": "  Fulfilled wishes:",
    "explain.violated": "  Violated not-desired wishes:",
    "explain.neutral": "  Neutral partners: {names}",
    "explain.entry": "    {label}: {names}",
    "explain.no_wishes": "  No wishes fulfilled.",
    "explain.no_survey": "  No team survey submitted — the score therefore stays 0.",
    "explain.unfulfilled": "  Unfulfilled wishes:",
    "explain.respected": "  Respected not-desired wishes:",
    "explain.pole_position": "  Pole position: alone in their role on the position.",
    "explain.needs_coaching": "  Coaching need: with {names} in the same role.",
    # -- UI: navigation ------------------------------------------------------------------
    "nav.home": "Home",
    "nav.team": "Team",
    "nav.survey": "Survey",
    "nav.solution": "Solution",
    "nav.analysis": "Analysis",
    "nav.section": "Partner assignment",
    # -- UI: shared ----------------------------------------------------------------------
    "ui.title": "dancepartner",
    "ui.subtitle": "Partnering a Latin formation team as an exact optimization problem.",
    "ui.language": "Language",
    "ui.no_team": "No team loaded yet — please load or create a team on “Home” first.",
    "ui.no_solution_yet": "No solution computed yet — please solve on “Solution” first.",
    "ui.unsaved": "Unsaved changes. They will be lost unless you download the team.",
    # -- UI: what this deployment can do (SPEC.md 14) ------------------------------------
    "ui.solver.unavailable": (
        "Computing an assignment is not available in the browser version: there is no "
        "WebAssembly build of the solver (OR-Tools). Editing the team, recording the survey "
        "and the feasibility pre-check all work here — to compute an assignment, download "
        "the team and run it locally, or use the hosted version."
    ),
    "ui.solver.editor_only": (
        "Browser version: teams and surveys can be edited here, an assignment cannot be computed."
    ),
    # -- browser boot screen ----------------------------------------------------------
    #
    # Shown by the static shell before Python exists, so wasm/build_static.py bakes both
    # tables in at build time and the shell steps through them on a timer. The wording has
    # to reassure a coach staring at a spinner, not describe a runtime to a developer.
    "ui.loading.start": "Getting the app ready …",
    "ui.loading.download": "Loading the app — about 30 MB, only on the first visit.",
    "ui.loading.solver": "Almost set up — preparing the solver …",
    "ui.loading.almost": "Nearly there. The next visit will be much quicker.",
    "ui.loading.noscript": "This app needs JavaScript.",
    "ui.draft.restored": (
        "Restored a draft from this browser. A draft is not a file — download the team to keep it."
    ),
    "ui.draft.hint": (
        "Changes stay in this browser, so reloading the page does not lose them. Nothing is "
        "written to disk."
    ),
    "ui.draft.discard": "Discard browser draft",
    "ui.draft.discarded": "Draft discarded.",
    "ui.draft.history": "Earlier versions",
    "ui.draft.history_hint": (
        "Loading a team keeps the previous one here. Editing overwrites the current version "
        "rather than adding another."
    ),
    "ui.draft.entry": "{n} dancers · {when}",
    "ui.draft.restore": "Restore",
    "ui.draft.restored_version": "Earlier version restored.",
    "ui.draft.gone": "That version has expired.",
    # -- UI: Home (load / create / feasibility) ------------------------------------------
    "ui.load.header": "Load team",
    "ui.load.upload": "Upload file",
    "ui.load.uploader": "Drop a team file (YAML) here",
    "ui.load.example": "Example team",
    "ui.load.example_button": "Load example team",
    "ui.load.example_hint": "20 fictional dancers on 8 positions — for trying things out.",
    "ui.load.create": "New team",
    "ui.load.create_button": "Create empty team",
    "ui.load.n_positions": "Positions",
    "ui.save.header": "Save",
    "ui.save.download": "Download team as YAML",
    "ui.save.comment_warning": (
        "The download loses any comments in the YAML file — PyYAML cannot preserve them. "
        "Keep real data in your own team file, not in the example."
    ),
    "ui.feasibility.header": "Pre-check",
    "ui.feasibility.involved": "involved: {names}",
    # -- UI: Team ------------------------------------------------------------------------
    "ui.team.header": "Dancers",
    "ui.team.col_id": "ID",
    "ui.team.col_name": "Name",
    "ui.team.col_role": "Role",
    "ui.team.col_pole_position": "Pole position",
    "ui.team.col_coaching": "Coaching need",
    "ui.team.help_pole_position": (
        "Must be alone in their role on the position (no doubled position)."
    ),
    "ui.team.help_coaching": "Must NOT be alone in their role on the position.",
    "ui.team.apply": "Apply changes",
    "ui.team.applied": "{n} dancers applied.",
    "ui.team.flags_exclusive": ("{name}: pole position and coaching need are mutually exclusive."),
    "ui.team.duplicate_id": "The ID “{dancer_id}” appears more than once.",
    "ui.team.empty_field": "Row {row}: ID and name must not be empty.",
    "ui.team.orphan_survey": (
        "{n} team survey(s) were removed because the dancer no longer exists."
    ),
    # -- UI: Survey ----------------------------------------------------------------------
    "ui.survey.header": "Team survey",
    "ui.survey.pick": "Dancer",
    "ui.survey.desired": "Desired partners",
    "ui.survey.not_desired": "Not-desired partners",
    "ui.survey.tier_help": "The lower the number, the stronger.",
    "ui.survey.add_tier": "Add another",
    "ui.survey.remove_tier": "Remove last",
    "ui.survey.apply": "Apply team survey",
    "ui.survey.applied": "Team survey for {name} applied.",
    "ui.survey.cleared": "Team survey for {name} removed.",
    "ui.survey.empty_tier": (
        "{label} is empty. Empty entries are dropped on apply; the rest move up."
    ),
    "ui.survey.duplicate_in_direction": (
        "{names}: named more than once in the same list. Each dancer may appear at one rank only."
    ),
    "ui.survey.in_both_directions": (
        "{names}: listed under both desired and not-desired partners."
    ),
    "ui.survey.count": "{n} of {total} have answered.",
    "ui.survey.answered": "answered",
    "ui.survey.unanswered": "pending",
    # -- UI: Solution --------------------------------------------------------------------
    "ui.solve.header": "Objective and solver",
    "ui.solve.run": "Compute partner assignment",
    "ui.solve.objective": "Objective",
    "ui.solve.aggregation": "Score aggregation",
    "ui.solve.scope": "Counted wishes",
    "ui.solve.veto_tier": "Hard vetoes up to no-go",
    "ui.solve.veto_none": "none",
    "ui.solve.top": "Search equally good solutions",
    "ui.solve.time_limit": "Time limit (seconds)",
    "ui.solve.near_optimal": "Near-optimal from fraction",
    "ui.solve.tier_slack": "Slack between wish ranks",
    "ui.solve.normalize": "Halve scores on doubled positions",
    "ui.solve.prefer_coupled": "Prefer complete doubled positions",
    "ui.solve.advanced": "More settings",
    "ui.solve.cards_header": "Positions",
    "ui.solve.doubled_badge": "doubled",
    "ui.solve.groups_hint": (
        "Dancers sharing a number can be swapped freely — every arrangement is equally "
        "good. Details on the Analysis page."
    ),
    "ui.solve.fulfilled_badge": "fulfilled",
    "ui.solve.violated_badge": "violated",
    "ui.solve.stages_header": "Objective in stages",
    "ui.solve.col_stage": "Stage",
    "ui.solve.col_value": "Value",
    "ui.solve.col_sense": "Direction",
    "ui.solve.col_locked": "locked in",
    # -- UI: objective / enum labels ------------------------------------------------------
    "ui.objective.weighted_sum": "Sum of scores",
    "ui.objective.maximin_then_sum": "The least satisfied first, then the sum",
    "ui.objective.leximin": "Fairest distribution (protect the least satisfied)",
    "ui.objective.lexicographic_tiers": "Wish ranks in order",
    "ui.aggregation.best": "best fulfilled wish",
    "ui.aggregation.sum": "sum of fulfilled wishes",
    "ui.scope.cross_role_only": "cross-role only",
    "ui.scope.all": "all",
    # -- UI: Analysis --------------------------------------------------------------------
    "ui.analysis.header": "Satisfaction",
    "ui.analysis.hint": "Least satisfied first — that is the row you need.",
    "ui.analysis.col_position": "Position",
    "ui.analysis.col_satisfaction": "Satisfaction",
    "ui.analysis.col_group": "Exchange group",
    "ui.analysis.col_fulfilled": "Fulfilled wishes",
    "ui.analysis.col_violated": "Violated not-desired wishes",
    "ui.analysis.groups_header": "Exchange groups",
    "ui.analysis.groups_none": (
        "Nothing to swap — no rearrangement of this solution is equally good."
    ),
    "ui.analysis.shortlist_header": "Equally good solutions",
    "ui.analysis.pick": "Solution",
    "ui.analysis.only_one": "There is only one solution — nothing to compare here.",
    "ui.analysis.diff_header": "Difference to solution {index}",
    "ui.analysis.diff_none": "No difference.",
    "ui.analysis.col_from": "from",
    "ui.analysis.col_to": "to",
    "ui.analysis.detail_header": "Individual dancer",
    # -- language names (native in both tables, so the toggle is always readable) ---------
    "language.en": "English",
    "language.de": "Deutsch",
    # -- CLI help ------------------------------------------------------------------------
    "help.app": "Partnering a Latin formation team as an exact optimization problem.",
    "help.check": "Checks a team file for countable obstacles.",
    "help.solve": "Computes an optimal partner assignment.",
    "help.explain": "Explains the result for a single dancer.",
    "help.team_file": "Path to the team file (YAML).",
    "help.result_file": "Path to the result file from “solve --json”.",
    "help.objective": "Objective function.",
    "help.aggregation": (
        "How a dancer's fulfilled wishes combine into their score. 'Best fulfilled wish' "
        "saturates: the top wish granted means fully satisfied, further fulfilled wishes add "
        "nothing. 'Sum' adds every fulfilled wish up."
    ),
    "help.scope": "Whether only cross-role wishes or all wishes are counted.",
    "help.veto_tier": "Not-desired wishes up to this rank become hard vetoes (0 = none).",
    "help.top": "How many equally good solutions to search for and print.",
    "help.near_optimal": (
        "Fraction of the optimum a solution must reach to make the list (1.0 = exact optima only)."
    ),
    "help.tier_slack": (
        "lexicographic-tiers only: how many fulfilled wishes one rank may give up so that a "
        "weaker rank wins."
    ),
    "help.solution": "Which solution from the result file to explain (1 = best).",
    "help.time_limit": "Solver time limit in seconds.",
    "help.backend": "Which solver to use: cpsat (default) or highs.",
    "help.seed": "Random seed for the solver.",
    "help.normalize": "Halve the score of a doubled position.",
    "help.prefer_coupled": "Prefer complete doubled positions (weakest stage).",
    "help.workers": "Number of parallel solver threads (1 = reproducible).",
    "help.json": "Additionally write the result as JSON to this path.",
    "help.dancer": "ID of the dancer to explain.",
    "help.verbose": "Log solver progress.",
}

_STRINGS_DE: dict[str, str] = {
    # -- feasibility diagnostics (feasibility.FeasibilityIssue.message) -------------------
    "feasibility.ROLE_COUNT_OUT_OF_RANGE": (
        "{role_label}: {n} Tänzer:innen auf {p} Positionen. Jede Position braucht eine oder "
        "zwei — möglich sind daher {p} bis {max_n}."
    ),
    "feasibility.TOO_MANY_POLE_POSITION": (
        "{role_label}: {count} mit Startanspruch, aber nur {available} Position(en) mit "
        "einfacher Besetzung ({n} {role_label} auf {p} Positionen)."
    ),
    "feasibility.TOO_MANY_COACHING": (
        "{role_label}: {count} mit Coachingbedarf brauchen je eine eigene Doppelbesetzung "
        "mit erfahrener Begleitung, es gibt aber nur {available} ({n} {role_label} auf {p} "
        "Positionen)."
    ),
    "feasibility.VETO_ALL_CROSS_ROLE": (
        "{name} hat alle {opposite_label} als Nicht-Wunschpartner (Veto) — jede Position ist "
        "aber mit beiden Rollen besetzt."
    ),
    "feasibility.VETO_COACHING_ISOLATED": (
        "{name} hat Coachingbedarf, aber keine:r der anderen {role_label} ist eine erfahrene "
        "Begleitung ohne Veto — es gibt keine mögliche Doppelbesetzung."
    ),
    "feasibility.VETO_FORCES_SINGLES": (
        "{role_label}: {count} Tänzer:innen können durch Startanspruch oder Vetos keine "
        "Doppelbesetzung bilden, es gibt aber nur {available} Position(en) mit einfacher "
        "Besetzung."
    ),
    # -- roles ---------------------------------------------------------------------------
    "role.leader.plural": "Herren",
    "role.follower.plural": "Damen",
    "role.leader": "Herr",
    "role.follower": "Dame",
    # -- shared --------------------------------------------------------------------------
    "team.summary": (
        "{n_dancers} Tänzer:innen ({n_leaders} Herren, {n_followers} Damen) "
        "auf {n_positions} Positionen {labels}."
    ),
    "team.surveys": "{n_surveys} von {n_dancers} haben die Teambefragung beantwortet.",
    "error.file_not_found": "Datei nicht gefunden: {path}",
    "error.invalid_team": "Die Teamdatei ist ungültig:\n{detail}",
    "error.invalid_yaml": "Die Datei ist kein gültiges YAML: {detail}",
    "error.invalid_shape": "Die Datei hat nicht den erwarteten Aufbau: {detail}",
    "error.invalid_json": "Die Ergebnisdatei ist kein gültiges JSON: {detail}",
    # -- check ---------------------------------------------------------------------------
    "check.ok": "Keine zählbaren Hindernisse gefunden.",
    "check.caveat": (
        "Das schließt eine Lösung nicht zu — es heißt nur, dass keine reine "
        "Abzählung dagegen spricht. Endgültig entscheidet der Solver."
    ),
    "check.issues": "{count} Problem(e) gefunden:",
    "check.issue": "  [{code}] {message}",
    "check.involved": "      betroffen: {ids}",
    # -- solve ---------------------------------------------------------------------------
    "solve.running": "Suche eine optimale Verpartnerung …",
    "solve.working": "Suche eine optimale Verpartnerung …",
    "solve.working_hint": (
        "Das kann bis zu {seconds:.0f} Sekunden dauern. Die Seite bleibt so lange beschäftigt."
    ),
    "solve.infeasible_precheck": "Die Teamdatei ist nicht lösbar:",
    "solve.no_solution": "Keine Lösung gefunden (Status {status}).",
    "solve.status": "Status: {status} — {wall_time:.2f} s, {branches} Verzweigungen.",
    "solve.stages": "Zielfunktion in Stufen:",
    "solve.stage": "  {name}: {value} ({sense})",
    "solve.stage_locked": "  {name}: {value} ({sense}), davon zugesichert: mindestens {locked}",
    "solve.sense.maximize": "maximiert",
    "solve.sense.minimize": "minimiert",
    "solve.scores": "Gesamtpunkte: {total}   niedrigste Einzelpunktzahl: {minimum}",
    "solve.scale_note": (
        "Punkte sind auf der ×2-Skala des Solvers (Normalisierung der Doppelbesetzung)."
    ),
    "solve.scale_note_best": (
        "Punkte zählen den besten erfüllten Wunsch pro Tänzer:in, auf der ×2-Skala des "
        "Solvers; 100 % Zufriedenheit = 1. Wunsch erfüllt, nichts verletzt."
    ),
    "solve.positions": "Positionen:",
    "solve.position": "  Position {label}{doubled}",
    "solve.doubled": "  (Doppelbesetzung)",
    "solve.leaders": "     Herren: {names}",
    "solve.followers": "     Damen:  {names}",
    "solve.solution_count": "{count} gleichwertige Lösung(en) gefunden.",
    "solve.solution_count_truncated": (
        "Mindestens {count} gleichwertige Lösungen — die Liste ist bei {count} abgeschnitten. "
        "Mit --top mehr anfordern."
    ),
    "solve.near_optimal": (
        "Fast-optimale Lösungen bis {percent:.0f} % des Optimums sind zugelassen."
    ),
    "solve.solution_heading": "── Lösung {index} von {count}{marker}",
    "solve.solution_best": " (beste)",
    "solve.solution_scores": "   Gesamtpunkte {total}, niedrigste Einzelpunktzahl {minimum}",
    "solve.diff_header": "   Unterschied zu Lösung 1:",
    "solve.diff_entry": "     {name}: {from_label} → {to_label}",
    "solve.groups_header": "Tauschgruppen — frei tauschbar, jede Anordnung gleichwertig:",
    "solve.group_heading": "  Gruppe {number} ({role}): {names}",
    "solve.group_member": "{name} ({label})",
    "solve.written": "Ergebnis geschrieben nach {path}.",
    # -- satisfaction table --------------------------------------------------------------
    "table.header": "Zufriedenheit (unzufriedenste zuerst):",
    "tier.desired": "{rank}. Wunsch",
    "tier.not_desired": "{rank}. Nicht-Wunsch",
    "table.columns": "{name:<20} {score:>7}  {wishes}",
    "table.col_name": "Tänzer:in",
    "table.col_score": "Punkte",
    "table.col_wishes": "Erfüllt / verletzt",
    "table.fulfilled": "{label}: {names}",
    "table.violated": "{label} verletzt: {names}",
    "table.nothing": "—",
    # -- explain -------------------------------------------------------------------------
    "explain.unknown_dancer": "Unbekannte Tänzer:in-ID: {dancer_id}",
    "explain.unknown_solution": (
        "Die Ergebnisdatei enthält nur {count} Lösung(en), Lösung {index} gibt es nicht."
    ),
    "explain.solution_note": "(aus Lösung {index} von {count})",
    "explain.across_header": "  Über alle {count} Lösungen hinweg:",
    "explain.across_entry": "    {name}: in {hits} von {count} Lösungen",
    "explain.across_stable": (
        "  Diese Besetzung ist in allen {count} Lösungen gleich — hier gibt es nichts zu wählen."
    ),
    "explain.group": (
        "  Tauschgruppe {number}: {names} — frei tauschbar, jede Anordnung gleichwertig."
    ),
    "explain.heading": "{name} ({role}) — Position {label}",
    "explain.score": "  Punkte: {score}",
    "explain.satisfaction": "  Zufriedenheit: {percent} %",
    "explain.partners": "  Auf derselben Position: {names}",
    "explain.fulfilled": "  Erfüllte Wünsche:",
    "explain.violated": "  Verletzte Nicht-Wünsche:",
    "explain.neutral": "  Neutrale Partner:innen: {names}",
    "explain.entry": "    {label}: {names}",
    "explain.no_wishes": "  Keine Wünsche erfüllt.",
    "explain.no_survey": "  Keine Teambefragung abgegeben — die Punktzahl bleibt daher 0.",
    "explain.unfulfilled": "  Nicht erfüllte Wünsche:",
    "explain.respected": "  Eingehaltene Nicht-Wünsche:",
    "explain.pole_position": "  Startanspruch: alleine in der eigenen Rolle auf der Position.",
    "explain.needs_coaching": "  Coachingbedarf: mit {names} in der eigenen Rolle.",
    # -- UI: navigation ------------------------------------------------------------------
    "nav.home": "Start",
    "nav.team": "Team",
    "nav.survey": "Umfrage",
    "nav.solution": "Lösung",
    "nav.analysis": "Analyse",
    "nav.section": "Verpartnerung",
    # -- UI: shared ----------------------------------------------------------------------
    "ui.title": "dancepartner",
    "ui.subtitle": "Verpartnerung einer Lateinformation als exaktes Optimierungsproblem.",
    "ui.language": "Sprache",
    "ui.no_team": "Noch kein Team geladen — bitte zuerst auf »Start« ein Team laden oder anlegen.",
    "ui.no_solution_yet": "Noch keine Lösung berechnet — bitte zuerst auf »Lösung« rechnen lassen.",
    "ui.unsaved": (
        "Ungespeicherte Änderungen. Sie gehen verloren, wenn Sie das Team nicht herunterladen."
    ),
    # -- UI: was diese Installation kann (SPEC.md 14) -------------------------------------
    "ui.solver.unavailable": (
        "Hier ist kein Solver installiert, eine Verpartnerung lässt sich also nicht berechnen. "
        "Team bearbeiten, Umfrage erfassen und die Vorprüfung funktionieren — für eine "
        "Verpartnerung bitte das Paket samt Solver installieren oder die gehostete Version "
        "nutzen."
    ),
    "ui.solver.editor_only": (
        "Nur Editor: Es ist kein Solver installiert, Teams und Umfragen lassen sich hier also "
        "bearbeiten, eine Verpartnerung aber nicht berechnen."
    ),
    # -- browser boot screen ----------------------------------------------------------
    "ui.loading.start": "Die App wird vorbereitet …",
    "ui.loading.download": "Die App wird geladen — rund 30 MB, nur beim ersten Besuch.",
    "ui.loading.solver": "Fast fertig — der Solver wird eingerichtet …",
    "ui.loading.almost": "Gleich geschafft. Der nächste Besuch geht deutlich schneller.",
    "ui.loading.noscript": "Diese App benötigt JavaScript.",
    "ui.draft.restored": (
        "Ein Entwurf aus diesem Browser wurde wiederhergestellt. Ein Entwurf ist keine Datei "
        "— bitte laden Sie das Team herunter, um es zu behalten."
    ),
    "ui.draft.hint": (
        "Änderungen bleiben in diesem Browser erhalten, ein Neuladen verliert sie also nicht. "
        "Auf die Festplatte wird nichts geschrieben."
    ),
    "ui.draft.discard": "Browser-Entwurf verwerfen",
    "ui.draft.discarded": "Entwurf verworfen.",
    "ui.draft.history": "Frühere Stände",
    "ui.draft.history_hint": (
        "Ein geladenes Team lässt das vorherige hier stehen. Bearbeiten überschreibt den "
        "aktuellen Stand, statt einen weiteren anzulegen."
    ),
    "ui.draft.entry": "{n} Tänzer:innen · {when}",
    "ui.draft.restore": "Wiederherstellen",
    "ui.draft.restored_version": "Früherer Stand wiederhergestellt.",
    "ui.draft.gone": "Dieser Stand ist abgelaufen.",
    # -- UI: Start (load / create / feasibility) -----------------------------------------
    "ui.load.header": "Team laden",
    "ui.load.upload": "Datei hochladen",
    "ui.load.uploader": "Teamdatei (YAML) hierher ziehen",
    "ui.load.example": "Beispielteam",
    "ui.load.example_button": "Beispielteam laden",
    "ui.load.example_hint": "20 erfundene Tänzer:innen auf 8 Positionen — zum Ausprobieren.",
    "ui.load.create": "Neues Team",
    "ui.load.create_button": "Leeres Team anlegen",
    "ui.load.n_positions": "Positionen",
    "ui.save.header": "Speichern",
    "ui.save.download": "Team als YAML herunterladen",
    "ui.save.comment_warning": (
        "Beim Herunterladen gehen Kommentare in der YAML-Datei verloren — PyYAML kann sie "
        "nicht erhalten. Echte Daten gehören in die eigene Teamdatei, nicht ins Beispiel."
    ),
    "ui.feasibility.header": "Vorprüfung",
    "ui.feasibility.involved": "betroffen: {names}",
    # -- UI: Team ------------------------------------------------------------------------
    "ui.team.header": "Tänzer:innen",
    "ui.team.col_id": "ID",
    "ui.team.col_name": "Name",
    "ui.team.col_role": "Rolle",
    "ui.team.col_pole_position": "Startanspruch",
    "ui.team.col_coaching": "Coachingbedarf",
    "ui.team.help_pole_position": (
        "Muss allein in der eigenen Rolle auf der Position sein (keine Doppelbesetzung)."
    ),
    "ui.team.help_coaching": "Darf NICHT allein in der eigenen Rolle auf der Position sein.",
    "ui.team.apply": "Änderungen übernehmen",
    "ui.team.applied": "{n} Tänzer:innen übernommen.",
    "ui.team.flags_exclusive": (
        "{name}: Startanspruch und Coachingbedarf schließen sich gegenseitig aus."
    ),
    "ui.team.duplicate_id": "Die ID »{dancer_id}» kommt mehrfach vor.",
    "ui.team.empty_field": "Zeile {row}: ID und Name dürfen nicht leer sein.",
    "ui.team.orphan_survey": (
        "{n} Teambefragung(en) wurden entfernt, weil es die Tänzer:in nicht mehr gibt."
    ),
    # -- UI: Umfrage ---------------------------------------------------------------------
    "ui.survey.header": "Teambefragung",
    "ui.survey.pick": "Tänzer:in",
    "ui.survey.desired": "Wunschpartner:innen",
    "ui.survey.not_desired": "Nicht-Wunschpartner:innen",
    "ui.survey.tier_help": "Je kleiner die Zahl, desto stärker.",
    "ui.survey.add_tier": "Weitere hinzufügen",
    "ui.survey.remove_tier": "Letzte entfernen",
    "ui.survey.apply": "Teambefragung übernehmen",
    "ui.survey.applied": "Teambefragung für {name} übernommen.",
    "ui.survey.cleared": "Teambefragung für {name} entfernt.",
    "ui.survey.empty_tier": (
        "{label} ist leer. Leere Einträge werden beim Übernehmen verworfen; die übrigen rücken auf."
    ),
    "ui.survey.duplicate_in_direction": (
        "{names}: steht mehrfach in derselben Liste. Jede Person darf nur an einer Stelle stehen."
    ),
    "ui.survey.in_both_directions": (
        "{names}: steht gleichzeitig unter Wunsch- und Nicht-Wunschpartner:innen."
    ),
    "ui.survey.count": "{n} von {total} haben geantwortet.",
    "ui.survey.answered": "beantwortet",
    "ui.survey.unanswered": "offen",
    # -- UI: Lösung ----------------------------------------------------------------------
    "ui.solve.header": "Zielfunktion und Solver",
    "ui.solve.run": "Verpartnerung berechnen",
    "ui.solve.objective": "Zielfunktion",
    "ui.solve.aggregation": "Wertung",
    "ui.solve.scope": "Gewertete Wünsche",
    "ui.solve.veto_tier": "Harte Vetos bis Nicht-Wunsch",
    "ui.solve.veto_none": "keine",
    "ui.solve.top": "Gleichwertige Lösungen suchen",
    "ui.solve.time_limit": "Zeitlimit (Sekunden)",
    "ui.solve.near_optimal": "Fast-optimal ab Anteil",
    "ui.solve.tier_slack": "Spielraum zwischen Wunschrängen",
    "ui.solve.normalize": "Punkte bei Doppelbesetzung halbieren",
    "ui.solve.prefer_coupled": "Vollständige Doppelbesetzungen bevorzugen",
    "ui.solve.advanced": "Weitere Einstellungen",
    "ui.solve.cards_header": "Positionen",
    "ui.solve.doubled_badge": "Doppelbesetzung",
    "ui.solve.groups_hint": (
        "Gleich nummerierte Tänzer:innen lassen sich frei tauschen — jede Anordnung ist "
        "gleichwertig. Details auf der Analyse-Seite."
    ),
    "ui.solve.fulfilled_badge": "erfüllt",
    "ui.solve.violated_badge": "verletzt",
    "ui.solve.stages_header": "Zielfunktion in Stufen",
    "ui.solve.col_stage": "Stufe",
    "ui.solve.col_value": "Wert",
    "ui.solve.col_sense": "Richtung",
    "ui.solve.col_locked": "zugesichert",
    # -- UI: objective / enum labels ------------------------------------------------------
    "ui.objective.weighted_sum": "Summe der Punkte",
    "ui.objective.maximin_then_sum": "Erst die Unzufriedensten, dann die Summe",
    "ui.objective.leximin": "Fairste Verteilung (Unzufriedenste schützen)",
    "ui.objective.lexicographic_tiers": "Wunschränge der Reihe nach",
    "ui.aggregation.best": "bester erfüllter Wunsch",
    "ui.aggregation.sum": "Summe der erfüllten Wünsche",
    "ui.scope.cross_role_only": "nur rollenübergreifend",
    "ui.scope.all": "alle",
    # -- UI: Analyse ---------------------------------------------------------------------
    "ui.analysis.header": "Zufriedenheit",
    "ui.analysis.hint": "Unzufriedenste zuerst — das ist die Zeile, die Sie brauchen.",
    "ui.analysis.col_position": "Position",
    "ui.analysis.col_satisfaction": "Zufriedenheit",
    "ui.analysis.col_group": "Tauschgruppe",
    "ui.analysis.col_fulfilled": "Erfüllte Wünsche",
    "ui.analysis.col_violated": "Verletzte Nicht-Wünsche",
    "ui.analysis.groups_header": "Tauschgruppen",
    "ui.analysis.groups_none": (
        "Nichts zu tauschen — keine Umstellung dieser Lösung ist gleichwertig."
    ),
    "ui.analysis.shortlist_header": "Gleichwertige Lösungen",
    "ui.analysis.pick": "Lösung",
    "ui.analysis.only_one": "Es gibt nur eine Lösung — hier gibt es nichts zu vergleichen.",
    "ui.analysis.diff_header": "Unterschied zu Lösung {index}",
    "ui.analysis.diff_none": "Kein Unterschied.",
    "ui.analysis.col_from": "von",
    "ui.analysis.col_to": "nach",
    "ui.analysis.detail_header": "Einzelne Tänzer:in",
    # -- language names (native in both tables, so the toggle is always readable) ---------
    "language.en": "English",
    "language.de": "Deutsch",
    # -- CLI help ------------------------------------------------------------------------
    "help.app": "Verpartnerung einer Lateinformation als exaktes Optimierungsproblem.",
    "help.check": "Prüft eine Teamdatei auf zählbare Hindernisse.",
    "help.solve": "Berechnet eine optimale Verpartnerung.",
    "help.explain": "Erklärt das Ergebnis für eine einzelne Tänzer:in.",
    "help.team_file": "Pfad zur Teamdatei (YAML).",
    "help.result_file": "Pfad zur Ergebnisdatei aus »solve --json«.",
    "help.objective": "Zielfunktion.",
    "help.aggregation": (
        "Wie die erfüllten Wünsche einer Tänzer:in in ihre Punktzahl eingehen. »Bester "
        "erfüllter Wunsch« sättigt: Top-Wunsch erfüllt heißt voll zufrieden, weitere "
        "erfüllte Wünsche zählen nicht extra. »Summe« addiert jeden erfüllten Wunsch."
    ),
    "help.scope": "Ob nur rollenübergreifende oder alle Wünsche gewertet werden.",
    "help.veto_tier": "Nicht-Wünsche bis zu diesem Rang werden harte Vetos (0 = keine).",
    "help.top": "Wie viele gleichwertige Lösungen gesucht und ausgegeben werden.",
    "help.near_optimal": (
        "Anteil des Optimums, den eine Lösung erreichen muss, um in die Liste zu kommen "
        "(1.0 = nur exakte Optima)."
    ),
    "help.tier_slack": (
        "Nur für lexicographic-tiers: wie viele erfüllte Wünsche ein Rang abgeben darf, "
        "damit ein schwächerer Rang gewinnt."
    ),
    "help.solution": "Welche Lösung aus der Ergebnisdatei erklärt wird (1 = beste).",
    "help.time_limit": "Zeitlimit des Solvers in Sekunden.",
    "help.backend": "Welcher Solver: cpsat (Standard) oder highs.",
    "help.seed": "Zufalls-Startwert des Solvers.",
    "help.normalize": "Punkte einer Doppelbesetzung halbieren.",
    "help.prefer_coupled": "Vollständige Doppelbesetzungen bevorzugen (schwächste Stufe).",
    "help.workers": "Anzahl paralleler Solver-Threads (1 = reproduzierbar).",
    "help.json": "Ergebnis zusätzlich als JSON hierhin schreiben.",
    "help.dancer": "ID der Tänzer:in, die erklärt werden soll.",
    "help.verbose": "Solver-Fortschritt mitloggen.",
}

TABLES: dict[Language, dict[str, str]] = {
    Language.EN: _STRINGS_EN,
    Language.DE: _STRINGS_DE,
}


def _initial_language(raw: str | None) -> Language:
    """Map the raw environment value to a language, falling back to English.

    A typo'd or unset ``DANCEPARTNER_LANG`` must not crash the CLI, so anything that is not a
    known language code silently means English.
    """
    if raw is None:
        return Language.EN
    try:
        return Language(raw)
    except ValueError:
        return Language.EN


_language: Language = _initial_language(os.environ.get(ENV_VAR))


def get_language() -> Language:
    """Return the currently active language."""
    return _language


def set_language(language: Language) -> None:
    """Switch the active language for all subsequent :func:`t` calls.

    The Streamlit app calls this at the top of every rerun from the coach's session state.
    It cannot retro-translate strings that already resolved, notably Typer help texts.
    """
    global _language
    _language = language


def t(key: str, **params: object) -> str:
    """Return the string for ``key`` in the active language, formatted with ``params``.

    Raises:
        KeyError: The key is not defined. Failing loudly beats shipping a screen with a raw
            key in it, and the test suite checks that every key used is present.
    """
    return TABLES[_language][key].format(**params)
