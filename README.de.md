# dancepartner

> English version: [README.md](README.md)

Verpartnerung einer Lateinformation als exaktes Optimierungsproblem.

Acht Positionen, rund zwanzig Tänzer:innen und eine Teambefragung voller Wünsche, die sich nicht
alle gleichzeitig erfüllen lassen. `dancepartner` rechnet aus, welche Aufstellung die Wünsche am
besten trifft: nicht „gut genug“, sondern beweisbar optimal, mit dem CP-SAT-Solver von OR-Tools.

Das Werkzeug entscheidet nichts. Es macht sichtbar, was die Zahlen hergeben: wer unzufrieden
bleibt, warum, und ob es eine Alternative gibt. Die Aufstellung macht der Trainer.

## Was das Programm modelliert

Acht **Positionen**, bezeichnet mit A bis H. Absichtlich Buchstaben: Die Positionen sind
untereinander austauschbar, und eine Nummerierung verleitet dazu, eine Rangfolge hineinzulesen,
die es nicht gibt.

Jede Position ist in beiden Rollen besetzt, je Rolle mit einer oder zwei Personen. Zwei Herren
*und* zwei Damen auf einer Position sind eine **Doppelbesetzung**. Weil der Kader selten gleich
viele Herren und Damen hat, gilt die Grenze je Rolle getrennt: Eine Position darf zwei Herren und
nur eine Dame tragen.

| Begriff im Team | Im Code und in der Teamdatei | Bedeutung |
|---|---|---|
| Herr / Dame | `Role.LEADER` / `Role.FOLLOWER` | Die beiden Rollen, je Person fest. |
| Position | Index `p`, Label A–H | Einer von 8 Plätzen, ungeordnet. |
| Doppelbesetzung | `is_doubled` | Zwei Herren und zwei Damen auf einer Position. |
| Startanspruch | `is_pole_position` | Muss allein in der eigenen Rolle stehen. |
| Coachingbedarf | `needs_coaching` | Darf nicht allein in der eigenen Rolle stehen. |
| Wunschpartner | `desired_tiers` | Gestufte Wunschlisten, Tier 1 am stärksten. |
| Nicht-Wunschpartner | `not_desired_tiers` | Dasselbe, umgekehrt. |
| Teambefragung | `Survey` | Die Antworten einer Person. |
| Verpartnerung | `Solution` | Eine vollständige Zuordnung. |

Im Code, in den Dateien und in den Logs gibt es genau ein Vokabular, das englische. Alles, was
der Trainer zu sehen bekommt, gibt es auf Englisch (Voreinstellung) und Deutsch — siehe
[Sprache](#sprache).

Zwei Eigenschaften entscheiden über das Ergebnis und sind leicht zu übersehen:

* **Wünsche sind gerichtet.** Dass Anna sich Lukas wünscht, heißt nicht, dass Lukas sich Anna
  wünscht. Das Programm ergänzt nichts aus Symmetrie. Nur harte **Vetos** wirken beidseitig, und
  zwar zwangsläufig: Zwei Personen teilen sich eine Position oder nicht.
* **Wer nicht antwortet, bekommt 0 Punkte** — und steht damit ganz oben in der
  Zufriedenheitstabelle. Kein Fehler, sondern die ehrliche Auskunft, dass über diese Person
  nichts bekannt ist.

Die vollständige Spezifikation steht in [`SPEC.md`](SPEC.md).

## Installation

Python 3.11 oder neuer.

```bash
make install          # Virtualenv, Paket mit dev- und ui-Extras, pre-commit-Hooks
```

Von Hand:

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'     # oder '.[ui]' nur für die Oberfläche
```

`streamlit` ist keine Laufzeit-Abhängigkeit, sondern ein Extra. Brauchst du nur die
Kommandozeile, installiere mit `pip install -e .`. Umgekehrt lässt sich `app/` löschen, ohne dass
dem Kern etwas fehlt.

## Schnellstart

```bash
make ui                    # Oberfläche auf http://localhost:8501
make ui PORT=8600          # oder anderswo
```

Oder auf der Kommandozeile, die alles kann, was die Oberfläche kann:

```bash
.venv/bin/dancepartner check   data/team.example.yaml
.venv/bin/dancepartner solve   data/team.example.yaml --top 3 --json out.json
.venv/bin/dancepartner explain data/team.example.yaml out.json --dancer lukas-b
```

`make` ohne Argument listet alle Ziele auf.

## Sprache

Die Ausgabe ist standardmäßig Englisch. `DANCEPARTNER_LANG=de` schaltet die Kommandozeile —
einschließlich der Hilfetexte — auf Deutsch; die Streamlit-Oberfläche hat einen Sprachumschalter
in der Seitenleiste. Die Make-Ziele reichen die Variable durch:

```bash
DANCEPARTNER_LANG=de .venv/bin/dancepartner check data/team.example.yaml
make cli DP_LANG=de
```

Teamdateien sind davon unberührt: Das YAML-Vokabular ist englisch und in beiden Sprachen
identisch. Die Beispielausgaben in dieser Datei sind die deutschen, also mit
`DANCEPARTNER_LANG=de` erzeugt.

## Ein durchgerechnetes Beispiel

`data/team.example.yaml` enthält ein erfundenes Team: 20 Tänzer:innen, 19 beantwortete
Teambefragungen. Die folgenden Ausgaben sind echt.

### Vorprüfung

```console
$ dancepartner check data/team.example.yaml
20 Tänzer:innen (9 Herren, 11 Damen) auf 8 Positionen A B C D E F G H.
19 von 20 haben die Teambefragung beantwortet.

Keine zählbaren Hindernisse gefunden.
Das schließt eine Lösung nicht zu — es heißt nur, dass keine reine Abzählung dagegen
spricht. Endgültig entscheidet der Solver.
```

`check` prüft nur, was sich abzählen lässt: Passen die Rollenzahlen auf die Positionen? Gibt es
genug einfach besetzte Positionen für alle mit Startanspruch? Das ist notwendig, aber nicht
hinreichend; die Lösbarkeit beweist erst der Solver. Der Vorteil: „5 Herren haben Startanspruch,
aber nur 4 Positionen sind einfach besetzt“ sagt, welches Häkchen weg muss. Ein blankes
INFEASIBLE sagt gar nichts.

### Rechnen

```console
$ dancepartner solve data/team.example.yaml --top 3
Status: OPTIMAL — 0.08 s, 8127 Verzweigungen.
Zielfunktion in Stufen:
  maximin: 0 (maximiert)
  sum: 55 (maximiert)
  coupled: 4 (minimiert)

3 gleichwertige Lösung(en) gefunden.

── Lösung 1 von 3 (beste)
   Gesamtpunkte 55, niedrigste Einzelpunktzahl 0
Positionen:
  Position A
     Herren: Lukas Brandt
     Damen:  Anna Brenner
  Position C
     Herren: Tim Rothe
     Damen:  Lena Fricke, Mia Thalmann
  …
  Position H
     Herren: Jan Hübner, Paul Mertens
     Damen:  Hanna Zeller
```

Drei Dinge sind hier wichtig.

**`maximin: 0` heißt nicht, dass die Rechnung schiefging.** Marie Günther hat keine Teambefragung
abgegeben, also ist ihre Punktzahl 0 und das erreichbare Minimum ebenfalls. Die Stufe hat ihr
Bestes getan; der Boden liegt eben dort.

**Die Punkte stehen auf der ×2-Skala des Solvers.** Bei linearer Gewichtung ist ein Wunsch in
Tier *k* zunächst `K − k + 1` wert, wobei `K` das höchste Tier der Instanz ist; das Ergebnis wird
verdoppelt, damit es sich auf einer Doppelbesetzung ohne Rundung halbieren lässt. In diesem Team
geht Tier 2 am weitesten, ein erfüllter Tier-1-Wunsch bringt also 4 Punkte. Deshalb steht bei
Lukas Brandt unten eine 4.

**„3 gleichwertige Lösungen“ heißt genau das.** Alle drei erreichen 55 Punkte. Sie sind nicht
Platz 1 bis 3, sondern drei gleich gute Antworten, zwischen denen die Zahlen nicht entscheiden
können. Der Trainer schon.

### Nachfragen

```console
$ dancepartner explain data/team.example.yaml out.json --dancer lukas-b
(aus Lösung 1 von 3)

Lukas Brandt (Herr) — Position A
  Punkte: 4
  Auf derselben Position: Anna Brenner
  Erfüllte Wünsche:
    Tier 1: Anna Brenner
  Nicht erfüllte Wünsche:
    Tier 2: Lena Fricke, Mia Thalmann
  Eingehaltene Nicht-Wünsche:
    Tier 1: Emma Köhler

  Diese Besetzung ist in allen 3 Lösungen gleich — hier gibt es nichts zu wählen.
```

Der letzte Satz ist der Grund, warum das Programm überhaupt mehrere Lösungen aufzählt. Eine
Partnerin, die in jeder optimalen Lösung dieselbe ist, ist keine Entscheidung, die der Trainer
treffen muss. Eine, die in 3 von 20 Lösungen vorkommt, schon. Bei diesem Team bleibt wenig zu
wählen: Emma Köhler wechselt zwischen Position D und E, Lena Fricke zwischen C und D. Mehr
Unterschiede gibt es nicht.

## Die vier Zielfunktionen

Die Zielfunktion legt fest, was „am besten“ heißt. Sie ändert das Ergebnis, nicht die Regeln:
Harte Nebenbedingungen gelten immer.

| `--objective` | Maximiert | Wann sinnvoll |
|---|---|---|
| `weighted-sum` | die Summe aller Punkte | Die Gesamtzufriedenheit zählt, einzelne Ausreißer sind hinnehmbar. |
| `maximin-then-sum` | erst die niedrigste Punktzahl, dann die Summe | Voreinstellung. Hebt zuerst den Boden, verschenkt danach nichts. |
| `leximin` | den sortierten Punktevektor, von unten nach oben | Auch der Zweit- und Drittunzufriedenste zählt. |
| `lexicographic-tiers` | Tier für Tier die Zahl erfüllter Wünsche | Ein Tier-1-Wunsch wiegt schwerer als beliebig viele Tier-2-Wünsche. |

`maximin-then-sum` und `leximin` sind nicht dasselbe. Beide heben zuerst das Minimum, aber
`maximin-then-sum` maximiert danach nur die Summe und darf dabei den Zweitschlechtesten opfern.
`leximin` arbeitet sich weiter nach oben und gibt dafür notfalls Gesamtpunkte auf. Den Fall, in
dem sich beide messbar unterscheiden, hält `tests/test_objectives.py::divergent_instance` fest.

Weitere Stellschrauben: `--weights` (linear oder geometrisch), `--scope` (nur rollenübergreifende
Wünsche oder alle), `--veto-tier N` (Nicht-Wünsche bis Tier N werden harte Bedingungen, `0`
schaltet sie ab), `--top N`, `--near-optimal` und `--tier-slack`. `dancepartner solve --help`
erklärt alle.

## Performance

Gemessen auf einem Apple-Silicon-Laptop (arm64, macOS), Python 3.11.9, OR-Tools 9.15,
`num_workers = 1` für Reproduzierbarkeit, bester von drei Läufen. Die Zeiten meldet
`SolveResult.wall_time`, also die Summe über alle Solver-Stufen. Beide Instanzen liegen im
Repository: `data/team.example.yaml` (20 Tänzer:innen, Tiers bis 2) und
`data/team.large.example.yaml` (24 Tänzer:innen, Tiers bis 3).

| Zielfunktion | 20 Tänzer:innen | Verzweigungen | 24 Tänzer:innen | Verzweigungen |
|---|---:|---:|---:|---:|
| `weighted-sum` | 0,04 s | 5 811 | **12,5 s** | 988 656 |
| `maximin-then-sum` | 0,05 s | 6 230 | **12,3 s** | 992 787 |
| `leximin` | 0,04 s | 887 | 0,17 s | 15 961 |
| `lexicographic-tiers` | 0,02 s | 565 | 0,05 s | 4 564 |

Alle vier finden auf der großen Instanz dieselbe Gesamtpunktzahl (101), brauchen dafür aber sehr
unterschiedlich lange. Und zwar entgegen der naheliegenden Vermutung: `leximin` läuft zwei Stufen
je Runde und wirkt teuer, ist hier aber rund 70-mal schneller als die simple Summe.

Der Grund ist die Beweislast. `weighted-sum` muss zeigen, dass es keine Aufstellung mit 102
Punkten gibt, und dafür bleibt ein riesiger Suchraum übrig. `leximin` legt dagegen Runde für
Runde den kompletten sortierten Punktevektor fest; jede dieser Bedingungen schneidet den
Suchraum drastisch zusammen, sodass am Ende kaum noch etwas zu beweisen ist.

Praktisch heißt das:

* Bis etwa 20 Tänzer:innen ist jede Zielfunktion unter einer Zehntelsekunde fertig.
  **Entscheide nach Inhalt, nicht nach Geschwindigkeit.**
* Braucht `maximin-then-sum` darüber zu lange, liefert `leximin` auf diesen Daten dasselbe
  Ergebnis in einem Bruchteil der Zeit, und ist inhaltlich sogar die strengere Aussage.
* Das Aufzählen kostet fast nichts: `--top 50` statt `--top 1` schlägt mit unter 0,2 s zu Buche,
  weil der zweite Durchgang auf einem Modell arbeitet, dessen Optima bereits feststehen.
* `--time-limit` ist die Notbremse, nicht der Normalfall. Läuft der Solver hinein, meldet er
  `FEASIBLE` statt `OPTIMAL`: Das Ergebnis ist gültig, aber nicht als bestes bewiesen. Hatte er
  noch keine Lösung, kommt keine zurück (Rückgabewert 3).

Nachrechnen:

```bash
make cli TEAM=data/team.large.example.yaml DANCER=carolin-r
```

## Die Oberfläche

`make ui` startet eine Startseite und vier Arbeitsseiten:

* **Start**: Teamdatei laden, hochladen oder neu anlegen, Vorprüfung, speichern.
* **Team**: die Tänzer:innen als Tabelle mit Name, Rolle, Startanspruch, Coachingbedarf.
* **Umfrage**: je Person und Richtung beliebig viele Tiers; Konflikte werden sofort gemeldet.
* **Lösung**: Zielfunktion einstellen, rechnen, die acht Positionen als Karten.
* **Analyse**: Zufriedenheit aufsteigend sortiert, dazu der Vergleich der gleichwertigen
  Lösungen.

Gespeichert wird nur auf Knopfdruck. PyYAML kann Kommentare nicht erhalten; ein Autosave würde
sie aus einer von Hand gepflegten Teamdatei stillschweigend entfernen. Echte Daten gehören nach
`data/team.yaml`: Der Pfad steht in `.gitignore`, versehentlich eingecheckte Befragungen wären
ein echtes Problem.

## Entwicklung

```bash
make check      # alles, was auch die CI prüft: ruff, mypy --strict, pytest, CLI
make test       # nur die Tests
make fmt        # formatieren
```

Der Kern liegt in `src/dancepartner/` und importiert nie `streamlit`; die Oberfläche in `app/`
hängt vom Kern ab, nie umgekehrt. Die CI prüft das, indem sie `app/` beiseiteschiebt,
`streamlit` deinstalliert und `solve` noch einmal laufen lässt.

Die Testabdeckung auf `src/dancepartner/` liegt bei 100 % (die Schwelle ist 90 %). Wichtiger als
die Zahl: Jeder Solver-Test ruft `tests/helpers.py::assert_result_valid` auf, das jede harte
Nebenbedingung unabhängig nachrechnet. Dem Solver wird nicht geglaubt, dass er modelliert hat,
was wir zu modellieren glaubten.

Die Spezifikation und die Design-Entscheidungen stehen in [`SPEC.md`](SPEC.md), die
Arbeitsregeln für Mitarbeit und Agenten in [`AGENTS.md`](AGENTS.md).

## Lizenz

MIT, siehe [`LICENSE`](LICENSE).
