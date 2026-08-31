"""German user-facing strings for the CLI and the Streamlit UI.

SPEC.md 2: all user-facing output is German and is routed through this module. Never inline a
German literal in a widget call or a ``print``; add a key here instead. Everything *about* the
code -- identifiers, comments, docstrings, log records, exception messages -- stays English.

Keys are namespaced by surface (``feasibility.``, ``cli.``) and the values are
``str.format`` templates. Call :func:`de`.
"""

from __future__ import annotations

__all__ = ["STRINGS", "de"]

STRINGS: dict[str, str] = {
    # -- feasibility diagnostics (feasibility.FeasibilityIssue.message_de) ----------------
    "feasibility.ROLE_COUNT_OUT_OF_RANGE": (
        "{role_de}: {n} Tänzer:innen auf {p} Positionen. Jede Position braucht eine oder "
        "zwei — möglich sind daher {p} bis {max_n}."
    ),
    "feasibility.TOO_MANY_POLE_POSITION": (
        "{role_de}: {count} mit Startanspruch, aber nur {available} Position(en) mit "
        "einfacher Besetzung ({n} {role_de} auf {p} Positionen)."
    ),
    "feasibility.TOO_MANY_COACHING": (
        "{role_de}: {count} mit Coachingbedarf brauchen mindestens {needed} "
        "Doppelbesetzung(en), es gibt aber nur {available} ({n} {role_de} auf {p} Positionen)."
    ),
    "feasibility.VETO_ALL_CROSS_ROLE": (
        "{name} hat alle {opposite_de} als Nicht-Wunschpartner (Veto) — jede Position ist "
        "aber mit beiden Rollen besetzt."
    ),
    "feasibility.VETO_COACHING_ISOLATED": (
        "{name} hat Coachingbedarf, aber zu allen anderen {role_de} besteht ein Veto — "
        "es gibt keine mögliche Doppelbesetzung."
    ),
    "feasibility.VETO_FORCES_SINGLES": (
        "{role_de}: {count} Tänzer:innen können durch Startanspruch oder Vetos keine "
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
    "solve.written": "Ergebnis geschrieben nach {path}.",
    # -- satisfaction table --------------------------------------------------------------
    "table.header": "Zufriedenheit (unzufriedenste zuerst):",
    "table.columns": "{name:<20} {score:>7}  {wishes}",
    "table.col_name": "Tänzer:in",
    "table.col_score": "Punkte",
    "table.col_wishes": "Erfüllt / verletzt",
    "table.fulfilled": "Tier {rank}: {names}",
    "table.violated": "verletzt Tier {rank}: {names}",
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
    "explain.heading": "{name} ({role}) — Position {label}",
    "explain.score": "  Punkte: {score}",
    "explain.partners": "  Auf derselben Position: {names}",
    "explain.fulfilled": "  Erfüllte Wünsche:",
    "explain.violated": "  Verletzte Nicht-Wünsche:",
    "explain.neutral": "  Neutrale Partner:innen: {names}",
    "explain.entry": "    Tier {rank}: {names}",
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
    "ui.no_team": "Noch kein Team geladen — bitte zuerst auf »Start« ein Team laden oder anlegen.",
    "ui.no_solution_yet": "Noch keine Lösung berechnet — bitte zuerst auf »Lösung« rechnen lassen.",
    "ui.unsaved": "Ungespeicherte Änderungen. Sie gehen verloren, wenn Sie nicht speichern.",
    "ui.saved_at": "Gespeichert nach {path}.",
    # -- UI: Start (load / create / feasibility) -----------------------------------------
    "ui.load.header": "Team laden",
    "ui.load.from_path": "Aus Datei laden",
    "ui.load.path": "Pfad zur Teamdatei (YAML)",
    "ui.load.button": "Laden",
    "ui.load.upload": "Datei hochladen",
    "ui.load.uploader": "Teamdatei (YAML) hierher ziehen",
    "ui.load.example": "Beispielteam",
    "ui.load.example_button": "Beispielteam laden",
    "ui.load.example_hint": "20 erfundene Tänzer:innen auf 8 Positionen — zum Ausprobieren.",
    "ui.load.create": "Neues Team",
    "ui.load.create_button": "Leeres Team anlegen",
    "ui.load.n_positions": "Positionen",
    "ui.load.loaded": "Team geladen: {path}",
    "ui.save.header": "Speichern",
    "ui.save.path": "Speichern nach",
    "ui.save.button": "Team speichern",
    "ui.save.comment_warning": (
        "Beim Speichern gehen Kommentare in der YAML-Datei verloren — PyYAML kann sie nicht "
        "erhalten. Echte Daten gehören nach data/team.yaml, nicht in die Beispieldatei."
    ),
    "ui.feasibility.header": "Vorprüfung",
    "ui.feasibility.involved": "betroffen: {names}",
    # -- UI: Team ------------------------------------------------------------------------
    "ui.team.header": "Tänzer:innen",
    "ui.team.hint": (
        "Die Reihenfolge ist bedeutsam: die Symmetriebrechung des Solvers numeriert die "
        "Positionen nach dem Index der Herren in dieser Liste."
    ),
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
    "ui.survey.tier": "Tier {rank}",
    "ui.survey.tier_help": "Tier 1 ist der stärkste Wunsch.",
    "ui.survey.add_tier": "Tier hinzufügen",
    "ui.survey.remove_tier": "Tier entfernen",
    "ui.survey.apply": "Teambefragung übernehmen",
    "ui.survey.applied": "Teambefragung für {name} übernommen.",
    "ui.survey.cleared": "Teambefragung für {name} entfernt.",
    "ui.survey.empty_tier": (
        "Tier {rank} ist leer. Leere Tiers werden beim Übernehmen verworfen; die übrigen "
        "rücken auf."
    ),
    "ui.survey.duplicate_in_direction": (
        "{names}: steht in mehreren Tiers derselben Richtung. Pro Richtung ist nur ein Tier "
        "je Tänzer:in erlaubt."
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
    "ui.solve.weights": "Gewichtung der Tiers",
    "ui.solve.scope": "Gewertete Wünsche",
    "ui.solve.veto_tier": "Vetos bis Tier",
    "ui.solve.veto_none": "keine",
    "ui.solve.top": "Gleichwertige Lösungen suchen",
    "ui.solve.time_limit": "Zeitlimit (Sekunden)",
    "ui.solve.near_optimal": "Fast-optimal ab Anteil",
    "ui.solve.tier_slack": "Tier-Spielraum",
    "ui.solve.normalize": "Punkte bei Doppelbesetzung halbieren",
    "ui.solve.prefer_coupled": "Vollständige Doppelbesetzungen bevorzugen",
    "ui.solve.advanced": "Weitere Einstellungen",
    "ui.solve.cards_header": "Positionen",
    "ui.solve.doubled_badge": "Doppelbesetzung",
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
    "ui.objective.leximin": "Leximin (Punktevektor der Reihe nach)",
    "ui.objective.lexicographic_tiers": "Tiers der Reihe nach",
    "ui.weights.linear": "linear",
    "ui.weights.geometric": "geometrisch",
    "ui.scope.cross_role_only": "nur rollenübergreifend",
    "ui.scope.all": "alle",
    # -- UI: Analyse ---------------------------------------------------------------------
    "ui.analysis.header": "Zufriedenheit",
    "ui.analysis.hint": "Unzufriedenste zuerst — das ist die Zeile, die Sie brauchen.",
    "ui.analysis.col_position": "Position",
    "ui.analysis.col_fulfilled": "Erfüllte Wünsche",
    "ui.analysis.col_violated": "Verletzte Nicht-Wünsche",
    "ui.analysis.shortlist_header": "Gleichwertige Lösungen",
    "ui.analysis.pick": "Lösung",
    "ui.analysis.only_one": "Es gibt nur eine Lösung — hier gibt es nichts zu vergleichen.",
    "ui.analysis.diff_header": "Unterschied zu Lösung {index}",
    "ui.analysis.diff_none": "Kein Unterschied.",
    "ui.analysis.col_from": "von",
    "ui.analysis.col_to": "nach",
    "ui.analysis.detail_header": "Einzelne Tänzer:in",
    # -- CLI help (German, like all user-facing text) ------------------------------------
    "help.app": "Verpartnerung einer Lateinformation als exaktes Optimierungsproblem.",
    "help.check": "Prüft eine Teamdatei auf zählbare Hindernisse.",
    "help.solve": "Berechnet eine optimale Verpartnerung.",
    "help.explain": "Erklärt das Ergebnis für eine einzelne Tänzer:in.",
    "help.team_file": "Pfad zur Teamdatei (YAML).",
    "help.result_file": "Pfad zur Ergebnisdatei aus »solve --json«.",
    "help.objective": "Zielfunktion.",
    "help.weights": "Gewichtungsschema für die Tiers.",
    "help.scope": "Ob nur rollenübergreifende oder alle Wünsche gewertet werden.",
    "help.veto_tier": "Nicht-Wünsche bis zu diesem Tier werden harte Vetos (0 = keine).",
    "help.top": "Wie viele gleichwertige Lösungen gesucht und ausgegeben werden.",
    "help.near_optimal": (
        "Anteil des Optimums, den eine Lösung erreichen muss, um in die Liste zu kommen "
        "(1.0 = nur exakte Optima)."
    ),
    "help.tier_slack": (
        "Nur für lexicographic-tiers: wie viele erfüllte Wünsche ein Tier abgeben darf, "
        "damit ein schwächeres Tier gewinnt."
    ),
    "help.solution": "Welche Lösung aus der Ergebnisdatei erklärt wird (1 = beste).",
    "help.time_limit": "Zeitlimit des Solvers in Sekunden.",
    "help.seed": "Zufalls-Startwert des Solvers.",
    "help.normalize": "Punkte einer Doppelbesetzung halbieren.",
    "help.prefer_coupled": "Vollständige Doppelbesetzungen bevorzugen (schwächste Stufe).",
    "help.workers": "Anzahl paralleler Solver-Threads (1 = reproduzierbar).",
    "help.json": "Ergebnis zusätzlich als JSON hierhin schreiben.",
    "help.dancer": "ID der Tänzer:in, die erklärt werden soll.",
    "help.verbose": "Solver-Fortschritt mitloggen.",
}


def de(key: str, **params: object) -> str:
    """Return the German string for ``key``, formatted with ``params``.

    Raises:
        KeyError: The key is not defined. Failing loudly beats shipping a screen with a raw
            key in it, and the test suite checks that every key used is present.
    """
    return STRINGS[key].format(**params)
