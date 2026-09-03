# dancepartner

[![CI](https://github.com/lukasbraach/dancepartner/actions/workflows/ci.yml/badge.svg)](https://github.com/lukasbraach/dancepartner/actions/workflows/ci.yml)
[![Pages](https://github.com/lukasbraach/dancepartner/actions/workflows/pages.yml/badge.svg)](https://github.com/lukasbraach/dancepartner/actions/workflows/pages.yml)
[![Docker](https://github.com/lukasbraach/dancepartner/actions/workflows/docker.yml/badge.svg)](https://github.com/lukasbraach/dancepartner/actions/workflows/docker.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![App öffnen](https://img.shields.io/badge/App%20%C3%B6ffnen-im%20Browser-FF4B4B?logo=streamlit&logoColor=white)](https://lukasbraach.github.io/dancepartner/)

> English version: [README.md](README.md)

Verpartnerung einer Lateinformation als exaktes Optimierungsproblem.

Acht Positionen, rund zwanzig Tänzer:innen und eine Teambefragung voller Wünsche, die sich nicht
alle gleichzeitig erfüllen lassen. `dancepartner` rechnet aus, welche Aufstellung die Wünsche am
besten trifft: nicht „gut genug“, sondern beweisbar optimal, mit dem CP-SAT-Solver von OR-Tools.

Das Werkzeug entscheidet nichts. Es macht sichtbar, was die Zahlen hergeben: wer unzufrieden
bleibt, warum, und ob es eine Alternative gibt. Die Aufstellung macht der Trainer.

> **Ausprobieren — ohne Installation.** [lukasbraach.github.io/dancepartner](https://lukasbraach.github.io/dancepartner/) führt die
> ganze App im Browser aus, Solver eingeschlossen. Beispielteam laden, »Verpartnerung berechnen«
> drücken, umsehen. Die Umfragedaten verlassen das Gerät nie: Hinter der Seite steht kein Server.
> Der erste Besuch lädt rund 30 MB, danach funktioniert sie offline und lässt sich wie eine App
> installieren. Dieselbe Oberfläche läuft auch lokal (`make ui`) oder auf dem eigenen Server
> ([Betrieb](#betrieb)).

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
| Coachingbedarf | `needs_coaching` | Darf nicht allein in der eigenen Rolle stehen, und die zweite Person derselben Rolle muss erfahren sein — zwei Coachingbedarfe teilen sich nie eine Position. |
| Wunschpartner | `desired_tiers` | Gestufte Wunschlisten, Tier 1 am stärksten. |
| Nicht-Wunschpartner | `not_desired_tiers` | Dasselbe, umgekehrt. |
| Trainervorgabe | `coach_constraints` | Eine harte Regel des Trainers: Diese Personen teilen sich eine Position (`together`), oder keine zwei von ihnen tun das (`apart`). |
| Teambefragung | `Survey` | Die Antworten einer Person. |
| Verpartnerung | `Solution` | Eine vollständige Zuordnung. |

Im Code, in den Dateien und in den Logs gibt es genau ein Vokabular, das englische. Alles, was
der Trainer zu sehen bekommt, gibt es auf Englisch (Voreinstellung) und Deutsch — siehe
[Sprache](#sprache).

Zwei Eigenschaften entscheiden über das Ergebnis und sind leicht zu übersehen:

* **Wünsche sind gerichtet.** Dass Anna sich Lukas wünscht, heißt nicht, dass Lukas sich Anna
  wünscht. Das Programm ergänzt nichts aus Symmetrie. Nur harte **Vetos** wirken beidseitig, und
  zwar zwangsläufig: Zwei Personen teilen sich eine Position oder nicht.
* **Eine Trainervorgabe sticht die Befragung.** `together` setzt Personen auf eine Position,
  `apart` hält sie davon fern — unabhängig davon, was sie angegeben haben. Anders als ein Veto
  wird sie aus keiner Antwort gelesen, der Veto-Rang greift also nicht. Eine Vorgabe benennt
  Personen und nie einen Positionsbuchstaben — die Positionen bleiben austauschbar.
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
Status: OPTIMAL — 0.03 s, 934 Verzweigungen.
Zielfunktion in Stufen:
  leximin.1.floor: 0 (maximiert)
  leximin.1.count: 16 (maximiert)
  leximin.2.floor: 2 (maximiert)
  leximin.2.count: 14 (maximiert)
  leximin.3.floor: 4 (maximiert)
  leximin.3.count: 0 (maximiert)
  coupled: 2 (minimiert)

2 gleichwertige Lösung(en) gefunden.

── Lösung 1 von 2 (beste)
   Gesamtpunkte 60, niedrigste Einzelpunktzahl 0
Positionen:
  Position A
     Herren: Lukas Brandt
     Damen:  Anna Brenner
  Position C
     Herren: Tim Rothe
     Damen:  Lena Fricke, Mia Thalmann
  …
  Position H  (Doppelbesetzung)
     Herren: Jan Hübner, Paul Mertens
     Damen:  Emma Köhler, Hanna Zeller
```

Drei Dinge sind hier wichtig.

**`leximin.1.floor: 0` heißt nicht, dass die Rechnung schiefging.** Marie Günther hat keine
Teambefragung abgegeben, also ist ihre Punktzahl 0 und das erreichbare Minimum ebenfalls. Die
Stufe hat ihr Bestes getan; der Boden liegt eben dort — und `leximin.1.count: 16` ist genau der
Zweck der voreingestellten Zielfunktion: 16 der 20 Tänzer:innen werden *über* diesen Boden
gehoben, Runde 2 zieht den Boden für die übrigen auf 2, Runde 3 auf 4.

**Die Punkte zählen den besten erfüllten Wunsch, auf der ×2-Skala des Solvers.** Ein Wunsch vom
Rang *k* ist `K − k + 1` wert, wobei `K` der tiefste Rang der Instanz ist; das Ergebnis wird
verdoppelt, damit die Normalisierung der Doppelbesetzung ohne Rundung halbieren kann. In diesem
Team geht der 2. Wunsch am weitesten, ein erfüllter 1. Wunsch bringt also
4 Punkte — und das ist in der Voreinstellung zugleich das Maximum: Die Zufriedenheit sättigt,
sobald der stärkste Wunsch erfüllt ist (`--aggregation best`). Wer seinen Top-Wunsch hat und
keinen verletzten Nicht-Wunsch, ist zu 100 % zufrieden, egal wie viele Alternativen er genannt
hat. `--aggregation sum` stellt die ältere Summen-Wertung wieder her.

**„2 gleichwertige Lösungen“ heißt genau das.** Beide erreichen 60 Punkte. Sie sind nicht
Platz 1 und 2, sondern zwei gleich gute Antworten, zwischen denen die Zahlen nicht entscheiden
können. Der Trainer schon.

### Nachfragen

```console
$ dancepartner explain data/team.example.yaml out.json --dancer lukas-b
(aus Lösung 1 von 2)

Lukas Brandt (Herr) — Position A
  Punkte: 4
  Zufriedenheit: 100 %
  Auf derselben Position: Anna Brenner
  Erfüllte Wünsche:
    1. Wunsch: Anna Brenner
  Nicht erfüllte Wünsche:
    2. Wunsch: Lena Fricke, Mia Thalmann
  Eingehaltene Nicht-Wünsche:
    1. Nicht-Wunsch: Emma Köhler

  Diese Besetzung ist in allen 2 Lösungen gleich — hier gibt es nichts zu wählen.
```

Der letzte Satz ist der Grund, warum das Programm überhaupt mehrere Lösungen aufzählt. Eine
Partnerin, die in jeder optimalen Lösung dieselbe ist, ist keine Entscheidung, die der Trainer
treffen muss. Eine, die in 3 von 20 Lösungen vorkommt, schon. Bei diesem Team bleibt genau
eine Wahl: Leah Dorn tanzt entweder als zweite Dame bei David Lorenz auf Position F oder neben
Marie Günther auf Position G.

Zusätzlich zur Shortlist markiert das Programm **Tauschgruppen**: Tänzer:innen, die sich frei
über ihre Positionen permutieren lassen — jede Anordnung hält jede harte Regel und den
Punktevektor, ein Tausch innerhalb der Gruppe kostet also gar nichts. Ihre Mitglieder tragen
die Gruppennummer (1️⃣, 2️⃣, …) direkt auf den Lösungskarten und im Reiter »Zufriedenheit«.
Dieses Beispielteam hat keine — Leah Dorns Wechsel verändert die Größe zweier Positionen,
statt zwei Personen zu tauschen, und genau dafür gibt es den Lösungs-Browser.

## Die vier Zielfunktionen

Die Zielfunktion legt fest, was „am besten“ heißt. Sie ändert das Ergebnis, nicht die Regeln:
Harte Nebenbedingungen gelten immer.

| `--objective` | Maximiert | Wann sinnvoll |
|---|---|---|
| `weighted-sum` | die Summe aller Punkte | Die Gesamtzufriedenheit zählt, einzelne Ausreißer sind hinnehmbar. |
| `maximin-then-sum` | erst die niedrigste Punktzahl, dann die Summe | Hebt den Boden einmal und kümmert sich danach nicht mehr um die Unzufriedensten. |
| `leximin` | den sortierten Punktevektor, von unten nach oben | **Voreinstellung.** Auch der Zweit- und Drittunzufriedenste zählt. |
| `lexicographic-tiers` | Rang für Rang die Zahl erfüllter Wünsche | Ein 1. Wunsch wiegt schwerer als beliebig viele 2. Wünsche. |

`maximin-then-sum` und `leximin` sind nicht dasselbe. Beide heben zuerst das Minimum, aber
`maximin-then-sum` maximiert danach nur die Summe und darf dabei den Zweitschlechtesten opfern.
`leximin` arbeitet sich weiter nach oben und gibt dafür notfalls Gesamtpunkte auf. Den Fall, in
dem sich beide messbar unterscheiden, hält `tests/test_objectives.py::divergent_instance` fest.

Weitere Stellschrauben: `--aggregation` (bester erfüllter Wunsch — die Voreinstellung — oder
Summe aller erfüllten Wünsche), `--scope` (alle Wünsche — die Voreinstellung — oder nur
rollenübergreifende), `--veto-tier N` (Nicht-Wünsche bis Rang N werden harte Bedingungen,
`0` schaltet sie ab), `--top N`, `--near-optimal` und `--tier-slack`.
`dancepartner solve --help` erklärt alle.

`--near-optimal` weitet die Auswahlliste um einen Prozentsatz je Stufenoptimum und greift
daher nur unter `maximin-then-sum`, dessen `sum`-Stufe groß genug ist. Die Stufenoptima von
leximin sind Einzelpunktzahlen, bei denen ein paar Prozent auf null abrunden.

## Performance

Gemessen auf einem Apple-Silicon-Laptop (arm64, macOS), Python 3.12.6, OR-Tools 9.15, HiGHS 1.11.0,
`num_workers = 1` für Reproduzierbarkeit, `--top 1`, bester von drei Läufen. Die Zeiten meldet
`SolveResult.wall_time`, also die Summe über alle Solver-Stufen. Beide Instanzen liegen im
Repository: `data/team.example.yaml` (20 Tänzer:innen, Wünsche bis Rang 2) und
`data/team.large.example.yaml` (24 Tänzer:innen, bis Rang 3).

Mit der voreingestellten Bester-Wunsch-Wertung ist jede Zielfunktion auf beiden Instanzen
schnell:

| Zielfunktion | 20 Tänzer:innen | Verzweigungen | 24 Tänzer:innen | Verzweigungen |
|---|---:|---:|---:|---:|
| `weighted-sum` | 0,01 s | 832 | 0,03 s | 3 037 |
| `maximin-then-sum` | 0,01 s | 1 114 | 0,04 s | 3 751 |
| `leximin` | 0,03 s | 929 | 0,06 s | 3 710 |
| `lexicographic-tiers` | 0,02 s | 814 | 0,04 s | 2 452 |

Der harte Fall ist die Summen-Wertung (`--aggregation sum`) auf der großen Instanz:

| Zielfunktion, `--aggregation sum` | 24 Tänzer:innen | Verzweigungen |
|---|---:|---:|
| `weighted-sum` | **1,1 s** | 108 983 |
| `maximin-then-sum` | **1,6 s** | 93 445 |
| `leximin` | 0,18 s | 16 774 |
| `lexicographic-tiers` | 0,05 s | 3 723 |

Alle vier finden dort dieselbe Gesamtsumme (101), brauchen dafür aber sehr unterschiedlich
lange. Und zwar entgegen der naheliegenden Vermutung: `leximin` läuft zwei Stufen je Runde und
wirkt teuer, ist hier aber rund sechsmal schneller als die simple Summe.

Der Grund ist die Beweislast. Unter `sum` muss `weighted-sum` zeigen, dass es keine Aufstellung
mit 102 Punkten gibt, und dafür bleibt ein riesiger Suchraum übrig. `leximin` legt dagegen Runde
für Runde den kompletten sortierten Punktevektor fest; jede dieser Bedingungen schneidet den
Suchraum drastisch zusammen, sodass am Ende kaum noch etwas zu beweisen ist. Die
Bester-Wunsch-Wertung ist aus demselben Grund von der anderen Seite her schnell: Die Punkte
nehmen viel weniger verschiedene Werte an, also schließen sich die Schranken zügig.

Praktisch heißt das:

* Mit der voreingestellten Wertung ist jede Zielfunktion auf beiden Instanzen deutlich unter
  einer Zehntelsekunde fertig. **Entscheide nach Inhalt, nicht nach Geschwindigkeit.**
* Unter `--aggregation sum` liefert `leximin` auf diesen Daten dieselbe Summe in einem Bruchteil
  der Zeit von `maximin-then-sum`, und ist inhaltlich sogar die strengere Aussage.
* Das Aufzählen kostet fast nichts: `--top 50` statt `--top 1` schlägt mit wenigen Millisekunden
  zu Buche, weil der zweite Durchgang auf einem Modell arbeitet, dessen Optima bereits feststehen.
* `--time-limit` ist die Notbremse, nicht der Normalfall. Läuft der Solver hinein, meldet er
  `FEASIBLE` statt `OPTIMAL`: Das Ergebnis ist gültig, aber nicht als bestes bewiesen. Hatte er
  noch keine Lösung, kommt keine zurück (Rückgabewert 3).

Nachrechnen:

```bash
make cli TEAM=data/team.large.example.yaml DANCER=carolin-r
```

### Die beiden Backends

Die Zahlen oben sind CP-SAT, die Voreinstellung. HiGHS rechnet dasselbe Modell als MILP und ist
das, was die Browser-Version verwendet, denn für OR-Tools gibt es keine WebAssembly-Fassung.
Gleiche Instanzen, gleiche Methode, Auswahl über `--backend`:

| Zielfunktion, Standard-Aggregation | cpsat 20 | highs 20 | cpsat 24 | highs 24 |
|------------------------------------|---------:|---------:|---------:|---------:|
| `leximin`                          |   0,03 s |   0,05 s |   0,06 s |   0,58 s |
| `weighted-sum`                     |   0,01 s |   0,02 s |   0,03 s |   0,17 s |
| `maximin-then-sum`                 |   0,01 s |   0,03 s |   0,04 s |   0,18 s |
| `lexicographic-tiers`              |   0,02 s |   0,04 s |   0,04 s |   0,56 s |

| Zielfunktion, `--aggregation sum` | cpsat 20 | highs 20 | cpsat 24 | highs 24 |
|-----------------------------------|---------:|---------:|---------:|---------:|
| `leximin`                         |   0,05 s |   0,07 s |   0,18 s |    1,8 s |
| `weighted-sum`                    |   0,03 s |   0,06 s |    1,1 s |    9,3 s |
| `maximin-then-sum`                |   0,05 s |   0,06 s |    1,6 s |   10,2 s |
| `lexicographic-tiers`             |   0,02 s |   0,06 s |   0,05 s |    2,4 s |

Beide Solver kommen in beiden Tabellen überall zum selben Ergebnis. HiGHS ist in den meisten
Zellen um den Faktor zwei bis zehn langsamer, in der schlechtesten um den Faktor fünfundvierzig
(`lexicographic-tiers` unter `sum` auf 24 Tänzer:innen), und bei der Standard-Aggregation ist das
der Unterschied zwischen sofort und immer noch sofort. Die Aufzählung hält sich besser als
erwartet: `--top 50` kostet auf der 20er-Instanz 0,06 s gegenüber 0,03 s bei CP-SAT — obwohl HiGHS
keinen Lösungspool hat und je Verpartnerung mit einem No-Good-Schnitt neu rechnen muss. Das Modell
ist zu diesem Zeitpunkt so festgezurrt, dass jeder weitere Lauf fast nichts kostet.

Die beiden `sum`-Zellen für `weighted-sum` und `maximin-then-sum` auf 24 Tänzer:innen waren
bisher der ehrliche Teil dieser Tabelle: 140 s und 146 s bei HiGHS, Einzelläufe oberhalb des
voreingestellten 30-s-Zeitlimits, und 12 s bei CP-SAT. Geändert hat sich das Modell, nicht die
Solver. Die Halbierung der Fremdrollen-Punkte einer doppelt besetzten Person war eine
Schaltvariable — vier Big-M-Zeilen im MILP, zwei bedingte Gleichungen in CP-SAT —, und deren
LP-Relaxation war schwach genug, um die gesamten Kosten dieser Zellen auszumachen. Als exaktes UND
je Gewichtsterm geschrieben (SPEC.md §8, *Normalisation*) kommt dasselbe Optimum auf beiden
Backends in einem Zehntel der Zeit, und jede Zelle bleibt jetzt innerhalb des voreingestellten
Zeitlimits. Unter `--aggregation sum` auf der größeren Instanz ist `leximin` weiterhin die
schnellste Wahl — und die ohnehin stärkere Aussage, und die Voreinstellung.

## Die Oberfläche

`make ui` startet eine Startseite und drei Arbeitsseiten, in der Reihenfolge der Arbeit: Team → Umfrage → Lösung.

* **Die Seitenleiste**, auf jeder Seite: die Sprache, was geladen ist, ob es gespeichert ist, der Download, der es
  speichert, ein kompaktes »Laden / neu / Beispiel«, die früheren Stände mit je einer Schaltfläche zurück und das
  Seitenmenü. Der letzte Schritt des Abends ist ein Download, und er verlangt nie den Weg zurück auf die erste Seite.
* **Start**: ein Überblick. Solange nichts geladen ist, die drei Wege hinein. Danach je eine Karte pro Schritt — wie
  viele Tänzer:innen und Regeln, wie viele Umfragen vorliegen, ob eine Lösung berechnet ist — mit Link auf die
  jeweilige Seite, dazu die Vorprüfung, die sagt, von welcher Veto-Stufe und welchen gewerteten Wünschen sie ausgeht.
* **Team**: die Tänzer:innen als Tabelle mit Name, Rolle, Startanspruch, Coachingbedarf; die Zahl der Positionen; und
  darunter die Trainervorgaben, die Tänzer:innen aus dieser Tabelle benennen. Ein **Übernehmen** für alles.
* **Umfrage**: je Person und Richtung beliebig viele Ränge; Konflikte werden sofort gemeldet. Ein Fortschrittsbalken,
  Zurück / Weiter / Nächste offene — und die Auswahl bleibt bei der Person, die Sie gerade übernommen haben.
* **Lösung**: die Einstellungen mit der Vorprüfung direkt daneben, das Rechnen, dann eine Lösungsauswahl und vier
  Reiter — die acht Positionen als Karten (wer sich kostenfrei tauschen lässt, ist mit 1️⃣, 2️⃣, … nummeriert), die
  Zufriedenheit aufsteigend sortiert, die Alternativen mit dem Unterschied zur gewählten Lösung, und eine Person
  erklärt. Das Ergebnis lässt sich als JSON herunterladen (dieselbe Datei, die `dancepartner solve --json` schreibt,
  `explain` liest sie also) oder als CSV der gewählten Lösung, eine Zeile pro Person.

Nichts, was Sie eingeben, erreicht das Team vor dem Übernehmen — und nichts davon geht vorher verloren: nicht
übernommene Änderungen überstehen den Wechsel auf eine andere Seite, und die Seitenleiste zählt sie, bis sie übernommen
sind.

Gespeichert wird nur auf Knopfdruck, und zwar als Download — die App hat keinen eigenen
beschreibbaren Pfad mehr, sobald sie im Browser läuft. PyYAML kann Kommentare nicht erhalten;
ein Autosave würde sie aus einer von Hand gepflegten Teamdatei stillschweigend entfernen.

Was die App von sich aus behält, ist ein **Entwurf**: das Team so, wie es gerade aussieht, damit
ein Neuladen nicht einen Abend Umfrageerfassung kostet. Ein Entwurf ist keine Speicherung — er
räumt die Warnung über ungespeicherte Änderungen nicht weg und wird nie in die Datei geschrieben,
aus der das Team stammt. In der Browser-Version liegt er im IndexedDB dieses Browsers, auf einem
Server im Arbeitsspeicher, adressiert über das `?draft=`-Merkmal in der URL. Beides erreicht keine
Festplatte. Die Solver-Einstellungen reisen mit dem Entwurf, ein Neuladen bringt also die gewählte
Zielfunktion zusammen mit dem Team zurück.

Ein geladenes Team lässt das vorherige stehen, ein Blick ins Beispiel wirft also nicht weg, was
Sie hatten. Bearbeiten überschreibt den aktuellen Stand, statt einen weiteren anzulegen; die
letzten zehn stehen in der Seitenleiste unter »Frühere Stände«, mit je einer Schaltfläche zurück.
Diese Liste gibt es anstelle des Zurück-Knopfes im Browser, weil Streamlit nicht erkennen kann,
auf welchen Stand ein Zurück-Schritt zeigt
([streamlit#13963](https://github.com/streamlit/streamlit/issues/13963)).

Echte Daten gehören nach `data/team.yaml`: Der Pfad steht in `.gitignore`, versehentlich
eingecheckte Befragungen wären ein echtes Problem.

## Betrieb

Dieselbe Oberfläche läuft auf drei Wegen, und alle drei können eine Verpartnerung berechnen — die
Browser-Version eingeschlossen. Sie rechnet mit [HiGHS](https://highs.dev) statt mit OR-Tools, denn
für OR-Tools gibt es keine WebAssembly-Fassung, für HiGHS schon. Beide liefern dasselbe Ergebnis;
wie das sichergestellt wird, steht in der [Spezifikation](SPEC.md).

| | `make ui` lokal | Browser (GitHub Pages) | Server (Docker) |
|---|---|---|---|
| Team laden, anlegen, hochladen, herunterladen | ✅ | ✅ | ✅ |
| Mannschaft und Umfrage bearbeiten | ✅ | ✅ | ✅ |
| Vorprüfung | ✅ | ✅ | ✅ |
| **Verpartnerung berechnen** | ✅ CP-SAT | ✅ HiGHS | ✅ CP-SAT |
| **Zufriedenheit, Tauschgruppen, Auswahlliste** | ✅ | ✅ | ✅ |
| Die Kommandozeile | ✅ | ❌ | ✅ per `docker exec` |
| Funktioniert offline | ✅ | ✅ nach dem ersten Besuch | ❌ braucht den Server |
| Die Spracheinstellung bleibt | ✅ in der URL | ✅ auch beim nächsten Besuch | ✅ in der URL |
| Neuladen behält das Team | ✅ im Speicher | ✅ IndexedDB, auf dem Gerät | ✅ im Speicher, über `?draft=` |
| Frühere Stände abrufbar | ✅ diese Sitzung | ✅ letzte 10, auch nach Neuladen | ✅ letzte 10, diese Sitzung |
| Umfragedaten verlassen den Rechner | nein | nein — sie verlassen das Gerät nicht | ja, zu Ihrem Server |
| Was eine Trainerin installieren muss | eine Python-Umgebung | nichts, nur eine URL | nichts, eine URL und ein Passwort |

Wo eine Fassung etwas nicht kann, steht das mit Begründung auf der Seite. Nichts wird
versteckt.

### Die Browser-Version

```bash
make wasm-serve     # bauen und auf http://localhost:8000 ausliefern
make wasm           # nur bauen, nach wasm/dist, für den Pages-Pfad
```

`.github/workflows/pages.yml` veröffentlicht sie bei jedem Push auf `main`. Der erste Aufruf lädt
rund 30 MB Pyodide und dauert ein paar Sekunden — hinter einer Ladeanzeige, die sagt, was gerade
passiert, denn eine leere Seite ist von einem kaputten Deployment nicht zu unterscheiden, und
»Unpacking archives« richtet sich nicht an eine Trainerin.

Ein Service Worker legt diese 30 MB im Vorbeigehen in den Cache, der zweite Besuch ist also schnell
und kommt ganz ohne Netz aus. Sie lässt sich als Web-App installieren, mit Manifest und richtigen
Icons. Auch Deep Links funktionieren: `/survey` lädt auf die Umfrageseite statt auf eine 404, auf
Pages wie unter `make wasm-serve`.

### Die Server-Version

```bash
cp docker/.env.example docker/.env     # und dann ausfüllen
docker run --rm caddy:2-alpine caddy hash-password --plaintext 'das-passwort'
make docker-up
```

Caddy übernimmt TLS und die Anmeldung — Basic Auth als Platzhalter, das Caddyfile markiert die
Stelle, an die OIDC gehört. Die Anmeldung wandert nie in die App. Der Container läuft als
Nicht-Root-Benutzer auf einem schreibgeschützten Dateisystem: Umfrageantworten liegen in seinem
Arbeitsspeicher und erreichen seine Festplatte nie.

Die Umgebungsvariablen sind in `docker/.env.example` dokumentiert; keine davon hat im Repository
einen echten Wert.

## Entwicklung

```bash
make check      # alles, was auch die CI prüft: ruff, mypy --strict, pytest, CLI
make test       # nur die Tests
make fmt        # formatieren
```

Der Kern liegt in `src/dancepartner/` und importiert nie `streamlit`; die Oberfläche in `app/`
hängt vom Kern ab, nie umgekehrt. Die CI prüft das, indem sie `app/` beiseiteschiebt,
`streamlit` deinstalliert und `solve` noch einmal laufen lässt.

Die Testabdeckung auf `src/dancepartner/` liegt bei 100 %, gemessen mit `make cov-both` — die
Suite gegen jedes Solver-Backend und zusammengeführt, denn allein erreicht das kein Lauf: Das
jeweils untätige Backend sieht tot aus. `make check` hält eine 90-%-Schwelle auf dem Einzellauf.
Wichtiger als die Zahl: Jeder Solver-Test ruft `tests/helpers.py::assert_result_valid` auf, das
jede harte Nebenbedingung unabhängig nachrechnet. Keinem der beiden Solver wird geglaubt, dass er
modelliert hat, was wir zu modellieren glaubten, und dieselben Tests gegen beide laufen zu lassen
ist die Art, wie sie auf dasselbe Ergebnis festgenagelt werden.

### Eine Abhängigkeit hinzufügen

Sie muss drei Hürden nehmen, nicht eine:

1. `pyproject.toml`, danach `requirements-dev.txt` neu einfrieren. Darauf pinnen CI und das
   Docker-Image.
2. **Läuft sie im Browser?** Wenn `src/dancepartner/` sie außerhalb eines Backend-Moduls
   importiert, muss sie in der Pyodide-Distribution vorkommen, die stlite lädt. In
   `wasm/pyodide-lock.trimmed.json` nachsehen, in `wasm/requirements-wasm.txt` auf *genau* diese
   Version pinnen; `tests/test_wasm_deps.py` prüft es nach. Ein reines Python-Rad
   (`py3-none-any`) von PyPI geht auch; eine kompilierte Erweiterung nicht, außer Pyodide baut
   sie.
3. **Wenn nicht**, bekommt sie die OR-Tools-Behandlung: auf ein Modul beschränkt, nur über einen
   Dispatcher erreichbar, der sie verzögert importiert, per `build_static.SERVER_ONLY` aus dem
   Bundle ausgeschlossen und in der Oberfläche hinter einem Capability-Flag. Nie ein nackter
   Import auf Modulebene in etwas, das die Browser-Seiten brauchen.

Die Spezifikation und die Design-Entscheidungen stehen in [`SPEC.md`](SPEC.md), die
Arbeitsregeln für Mitarbeit und Agenten in [`AGENTS.md`](AGENTS.md).

## Lizenz

MIT, siehe [`LICENSE`](LICENSE).
