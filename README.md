# dancepartner

Verpartnerung einer Lateinformation als exaktes Optimierungsproblem.

Acht Positionen, rund zwanzig Tänzer:innen, und eine Teambefragung voller Wünsche, die sich
nicht alle gleichzeitig erfüllen lassen. `dancepartner` rechnet aus, welche Aufstellung die
Wünsche am besten trifft — nicht „gut genug“, sondern beweisbar optimal, mit dem
CP-SAT-Solver von OR-Tools.

Das Werkzeug entscheidet nichts. Es macht sichtbar, was die Zahlen hergeben: wer unzufrieden
bleibt, warum, und ob es überhaupt eine Alternative gibt. Die Aufstellung macht der Trainer.

---

## Was das Programm modelliert

Acht **Positionen**, mit Buchstaben A–H bezeichnet. Die Buchstaben sind bewusst keine Zahlen:
die Positionen sind untereinander austauschbar, und eine Nummerierung verleitet dazu, eine
Rangfolge hineinzulesen, die es nicht gibt.

Jede Position ist mit beiden Rollen besetzt, je Rolle mit einer oder zwei Personen. Zwei Herren
*und* zwei Damen auf einer Position sind eine **Doppelbesetzung**. Weil der Kader selten
gleich viele Herren und Damen hat, gilt die Grenze je Rolle getrennt — eine Position darf zwei
Herren und nur eine Dame tragen.

| Begriff im Team | Im Code und in der YAML-Datei | Bedeutung |
|---|---|---|
| Herr / Dame | `Role.LEADER` / `Role.FOLLOWER` | Die beiden Rollen, je Person fest. |
| Position | Index `p`, Label A–H | Einer von 8 Plätzen, **ungeordnet und austauschbar**. |
| Doppelbesetzung | `is_doubled` | Position mit zwei Herren *und* zwei Damen. |
| Startanspruch | `is_pole_position` | Muss **allein** in der eigenen Rolle auf der Position sein. |
| Coachingbedarf | `needs_coaching` | Darf **nicht** allein in der eigenen Rolle sein. |
| Wunschpartner | `desired_tiers` | Gestufte Wunschlisten, Tier 1 am stärksten. |
| Nicht-Wunschpartner | `not_desired_tiers` | Dasselbe, umgekehrt. |
| Teambefragung | `Survey` | Die Antworten einer Person. |
| Verpartnerung | `Solution` | Eine vollständige Zuordnung. |

Die englischen Bezeichner sind Absicht: im Code, in den Dateien und in den Logs gibt es genau
**ein** Vokabular. Alles, was der Trainer zu sehen bekommt, ist Deutsch.

Zwei Eigenschaften sind leicht zu übersehen und entscheiden über das Ergebnis:

* **Wünsche sind gerichtet.** Dass Anna sich Lukas wünscht, heißt nicht, dass Lukas sich Anna
  wünscht. Das Programm ergänzt nichts und schließt nichts aus Symmetrie. Nur harte **Vetos**
  wirken beidseitig, und zwar zwangsläufig: zwei Personen teilen sich eine Position oder nicht.
* **Wer nicht antwortet, bekommt 0 Punkte** — und steht damit automatisch ganz oben in der
  Zufriedenheitstabelle. Das ist kein Fehler, sondern die ehrliche Auskunft, dass über diese
  Person nichts bekannt ist.

Die vollständige Spezifikation steht in [`SPEC.md`](SPEC.md).

---

## Installation

Python 3.11 oder neuer.

```bash
make install          # Virtualenv, Paket mit dev- und ui-Extras, pre-commit-Hooks
```

Von Hand geht es genauso:

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'     # oder '.[ui]' nur für die Oberfläche
```

`streamlit` ist bewusst **keine** Laufzeit-Abhängigkeit, sondern ein Extra. Wer nur die
Kommandozeile braucht, installiert mit `pip install -e .` und bekommt die Oberfläche nicht mit.
Umgekehrt lässt sich `app/` löschen, ohne dass am Kern irgendetwas fehlt.

---

## Schnellstart

```bash
make ui                    # Oberfläche auf http://localhost:8501
make ui PORT=8600          # oder anderswo
```

Oder auf der Kommandozeile — sie ist die Referenz-Schnittstelle und kann alles, was die
Oberfläche kann:

```bash
.venv/bin/dancepartner check   data/team.example.yaml
.venv/bin/dancepartner solve   data/team.example.yaml --top 3 --json out.json
.venv/bin/dancepartner explain data/team.example.yaml out.json --dancer lukas-b
```

`make` ohne Argument listet alle Ziele auf.

---

## Ein durchgerechnetes Beispiel

`data/team.example.yaml` enthält ein erfundenes Team: 20 Tänzer:innen, 19 beantwortete
Teambefragungen. Die folgenden Ausgaben sind echt.

### 1. Vorprüfung

```console
$ dancepartner check data/team.example.yaml
20 Tänzer:innen (9 Herren, 11 Damen) auf 8 Positionen A B C D E F G H.
19 von 20 haben die Teambefragung beantwortet.

Keine zählbaren Hindernisse gefunden.
Das schließt eine Lösung nicht zu — es heißt nur, dass keine reine Abzählung dagegen
spricht. Endgültig entscheidet der Solver.
```

`check` rechnet nur ab, was sich abzählen lässt: Passen die Rollenzahlen auf die Positionen?
Gibt es genug einfach besetzte Positionen für alle mit Startanspruch? Diese Prüfungen sind
**notwendig, aber nicht hinreichend** — sie finden echte Hindernisse, beweisen aber keine
Lösbarkeit. Dafür gibt es den Solver. Der Vorteil: „5 Herren haben Startanspruch, aber nur 4
Positionen sind einfach besetzt“ sagt, welches Häkchen weg muss. Ein blankes INFEASIBLE sagt
gar nichts.

### 2. Rechnen

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

**`maximin: 0`** heißt nicht, dass die Rechnung schiefging. Marie Günther hat keine
Teambefragung abgegeben, also ist ihre Punktzahl 0, also ist das erreichbare Minimum 0. Die
Stufe hat ihr Bestes getan; der Boden liegt eben dort.

**Die Punkte stehen auf der ×2-Skala** des Solvers. Bei linearer Gewichtung ist ein Wunsch in
Tier *k* zunächst `K − k + 1` wert, wobei `K` das höchste Tier der ganzen Instanz ist; das
Ergebnis wird dann verdoppelt, damit sich der Beitrag auf einer Doppelbesetzung ohne Rundung
halbieren lässt. In diesem Team geht Tier 2 am weitesten, also bringt ein erfüllter
Tier-1-Wunsch 2 × 2 = 4 Punkte — deshalb steht bei Lukas Brandt unten eine 4. Im großen
Beispielteam reichen die Tiers bis 3, dort wären es 6.

**„3 gleichwertige Lösungen“ heißt genau das.** Alle drei erreichen 55 Punkte. Sie sind nicht
Platz 1, 2 und 3, sondern drei gleich gute Antworten, zwischen denen die Zahlen nicht
entscheiden können — der Trainer schon.

### 3. Nachfragen

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

Der letzte Satz ist der eigentliche Grund, warum das Programm überhaupt mehrere Lösungen
aufzählt. Eine Partnerin, die in *jeder* optimalen Lösung dieselbe ist, ist keine
Entscheidung, die der Trainer treffen muss. Eine, die in 3 von 20 Lösungen vorkommt, schon.
Die Unterschiede zwischen den Lösungen sind bei diesem Team klein — Emma Köhler wechselt
zwischen Position D und E, Lena Fricke zwischen C und D. Mehr steht nicht zur Wahl.

---

## Die vier Zielfunktionen

Die Zielfunktion legt fest, was „am besten“ heißt. Sie ändert das Ergebnis, nicht die Regeln:
harte Nebenbedingungen gelten immer.

| `--objective` | Maximiert | Wann sinnvoll |
|---|---|---|
| `weighted-sum` | die Summe aller Punkte | Wenn die Gesamtzufriedenheit zählt und einzelne Ausreißer in Kauf genommen werden. |
| `maximin-then-sum` | erst die **niedrigste** Einzelpunktzahl, dann die Summe | Voreinstellung. Hebt zuerst den Boden, verschenkt aber danach nichts. |
| `leximin` | den ganzen sortierten Punktevektor der Reihe nach | Wenn nicht nur der Unzufriedenste zählt, sondern auch der Zweit- und Drittunzufriedenste. |
| `lexicographic-tiers` | Tier für Tier die Zahl erfüllter Wünsche | Wenn ein Tier-1-Wunsch grundsätzlich schwerer wiegt als beliebig viele Tier-2-Wünsche. |

`maximin-then-sum` und `leximin` sind nicht dasselbe. Beide heben zuerst das Minimum, aber
`maximin-then-sum` maximiert danach nur noch die Summe und darf dabei den Zweitschlechtesten
opfern. `leximin` arbeitet sich weiter nach oben und gibt dafür notfalls Gesamtpunkte auf. Auf
den Beispielteams fällt das nicht auf, weil beide dasselbe Optimum finden — den Fall, in dem
sie sich messbar unterscheiden, hält `tests/test_objectives.py::divergent_instance` fest.

Weitere Stellschrauben: `--weights` (linear oder geometrisch), `--scope` (nur
rollenübergreifende Wünsche oder alle), `--veto-tier N` (Nicht-Wünsche bis Tier N werden harte
Bedingungen, `0` schaltet sie ab), `--top N` (wie viele gleichwertige Lösungen),
`--near-optimal` und `--tier-slack`. `dancepartner solve --help` erklärt alle.

---

## Performance

Gemessen auf einem Apple-Silicon-Laptop (arm64, macOS), Python 3.11.9, OR-Tools 9.15,
`num_workers = 1` für Reproduzierbarkeit. Bester von drei Läufen. Die Zeiten sind die, die
`SolveResult.wall_time` meldet, also die Summe über alle Solver-Stufen.

Beide Instanzen liegen im Repository: `data/team.example.yaml` (20 Tänzer:innen, 19
Befragungen, Tiers bis 2) und `data/team.large.example.yaml` (24 Tänzer:innen, 22 Befragungen,
Tiers bis 3).

| Zielfunktion | 20 Tänzer:innen | Verzweigungen | 24 Tänzer:innen | Verzweigungen |
|---|---:|---:|---:|---:|
| `weighted-sum` | 0,04 s | 5 811 | **12,5 s** | 988 656 |
| `maximin-then-sum` | 0,05 s | 6 230 | **12,3 s** | 992 787 |
| `leximin` | 0,04 s | 887 | 0,17 s | 15 961 |
| `lexicographic-tiers` | 0,02 s | 565 | 0,05 s | 4 564 |

Alle vier finden auf der großen Instanz dieselbe Gesamtpunktzahl (101). Sie brauchen dafür
sehr unterschiedlich lange, und zwar entgegen der naheliegenden Vermutung: `leximin` läuft
zwei Stufen je Runde und wirkt teuer, ist hier aber rund **70-mal schneller** als die simple
Summe.

Der Grund ist die Beweislast. `weighted-sum` muss zeigen, dass es keine Aufstellung mit 102
Punkten gibt, und dafür bleibt ein riesiger Suchraum übrig — allein die `sum`-Stufe kostet
etwa 10,3 s, die `coupled`-Feinabstimmung noch einmal 2,3 s. `leximin` legt dagegen Runde für
Runde den kompletten sortierten Punktevektor fest; jede dieser Bedingungen schneidet den
Suchraum drastisch zusammen, sodass am Ende kaum noch etwas zu beweisen ist.
`lexicographic-tiers` zählt nur erfüllte Wünsche je Tier und ist damit noch stärker
eingegrenzt.

Praktische Folgerungen:

* **Bis etwa 20 Tänzer:innen ist die Wahl der Zielfunktion für die Laufzeit egal.** Alles ist
  unter einer Zehntelsekunde fertig. Entscheiden Sie nach Inhalt, nicht nach Geschwindigkeit.
* **Darüber lohnt ein Blick.** Wenn `maximin-then-sum` zu lange braucht, liefert `leximin` auf
  diesen Daten dasselbe Ergebnis in einem Bruchteil der Zeit — und ist inhaltlich sogar die
  strengere Aussage.
* **Das Aufzählen kostet fast nichts.** `--top 50` statt `--top 1` schlägt mit unter 0,2 s zu
  Buche, weil der zweite Durchgang auf einem Modell arbeitet, dessen Optima bereits feststehen.
* **`--time-limit` ist die Notbremse**, nicht der Normalfall. Läuft der Solver hinein, meldet
  er `FEASIBLE` statt `OPTIMAL` — das Ergebnis ist dann gültig, aber nicht als bestes bewiesen.
  Hatte er noch gar keine Lösung, kommt überhaupt keine zurück (Rückgabewert 3). Die
  Oberfläche gibt dasselbe Limit an den Solver weiter, damit sie nicht hängen kann.

Nachrechnen:

```bash
make cli TEAM=data/team.large.example.yaml DANCER=carolin-r
```

---

## Die Oberfläche

`make ui` startet eine Startseite und vier Arbeitsseiten:

* **Start** — Teamdatei laden, hochladen oder neu anlegen, Vorprüfung, ausdrücklich speichern.
* **Team** — die Tänzer:innen als Tabelle: Name, Rolle, Startanspruch, Coachingbedarf.
* **Umfrage** — je Person und Richtung beliebig viele Tiers; Konflikte werden sofort gemeldet.
* **Lösung** — Zielfunktion einstellen, rechnen, die acht Positionen als Karten.
* **Analyse** — Zufriedenheit aufsteigend sortiert, dazu ein Vergleich der gleichwertigen
  Lösungen.

Gespeichert wird **nur auf Knopfdruck**. Das ist wichtig: PyYAML kann Kommentare nicht
erhalten, ein automatisches Speichern würde die Kommentare aus einer von Hand gepflegten
Teamdatei stillschweigend entfernen. Echte Daten gehören nach `data/team.yaml` — dieser Pfad
steht in `.gitignore`, versehentlich eingecheckte Befragungen wären ein echtes Problem.

---

## Entwicklung

```bash
make check      # alles, was auch die CI prüft: ruff, mypy --strict, pytest, CLI
make test       # nur die Tests
make fmt        # formatieren
```

Der Kern liegt in `src/dancepartner/` und importiert **nie** `streamlit`; die Oberfläche in
`app/` hängt vom Kern ab, nie umgekehrt. Die CI prüft das, indem sie `app/` beiseite schiebt,
`streamlit` deinstalliert und `solve` noch einmal laufen lässt.

Die Testabdeckung auf `src/dancepartner/` liegt bei 100 % (die Schwelle ist 90 %). Wichtiger
als die Zahl: jeder Solver-Test ruft `tests/helpers.py::assert_result_valid` auf, das jede
harte Nebenbedingung unabhängig gegen das Ergebnis nachrechnet. Dem Solver wird nicht
geglaubt, dass er modelliert hat, was wir zu modellieren glaubten.

Für Mitarbeit an diesem Repository: [`CLAUDE.md`](CLAUDE.md) hält die Entscheidungen fest, die
sich aus dem Code nicht ablesen lassen, [`SPEC.md`](SPEC.md) ist der Vertrag.

## Lizenz

MIT, siehe [`LICENSE`](LICENSE).
