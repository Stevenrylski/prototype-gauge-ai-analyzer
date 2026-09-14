# Anleitung zum Prototyp

Kurzanleitung zum Aufsetzen und Benutzen des Prototyps, der im Rahmen der
Bachelorarbeit entstanden ist.

## Was das System macht

Automatisierte Testläufe mit dem Test-Framework *Gauge* erzeugen JSON-Reports.
Bei großen Testsuiten stehen darin schnell hunderte Fehlschläge, von denen die
meisten derselbe Fehler mit anderen Werten sind (andere Bestellnummer, anderer
Zeitstempel). Der Prototyp liest diese Reports und

1. **gruppiert gleichartige Fehler**, indem dynamische Werte vor dem Vergleich
   durch Platzhalter ersetzt werden (Normalisierung). Aus 99 Fehlschlägen mit
   verschiedenen Bestellnummern wird *eine* Gruppe, und der eine wirklich andere
   Fehler fällt sofort auf.
2. **führt mehrere Workspaces zusammen** und zeigt, in wie vielen Projekten
   derselbe Fehler auftritt.
3. **lässt jede Fehlergruppe von einer KI analysieren** (Klassifikation,
   wahrscheinliche Ursache, Handlungsempfehlung, Konfidenz). Rückfragen sind
   per Chat pro Fehlergruppe möglich.
4. **speichert jede Analyse dauerhaft**, sodass derselbe Fehler nicht erneut an
   die KI geschickt wird.

Vor dem Senden an die KI werden Pfade, Benutzernamen, Hostnames, E-Mail- und
IP-Adressen ersetzt. Die Oberfläche zeigt unter *"An die KI gesendet
(anonymisiert)"* jederzeit an, was tatsächlich übermittelt wurde.

## Voraussetzungen

* **Python 3.10 oder neuer**
* Ein Webbrowser
* *Optional:* [Gauge](https://gauge.org) - nur nötig, wenn ein eigener,
  frischer Testlauf erzeugt werden soll. Zum Ausprobieren des Analyzers wird
  Gauge **nicht** benötigt, da fertige Beispiel-Reports mitgeliefert sind.

Eine Internetverbindung ist nur für Variante B (echte KI) nötig.

## Variante A: Starten ohne API-Key (empfohlen zum Ausprobieren)

Der Prototyp bringt ein regelbasiertes Mock-Backend mit, das ohne API-Key und
ohne Internetverbindung funktioniert. Alle Funktionen der Oberfläche
(Gruppierung, Analyse, Chat, Ähnlichkeits-Check) sind damit bedienbar.

**macOS / Linux**

```bash
git clone https://github.com/Stevenrylski/prototype-gauge-ai-analyzer.git
cd prototype-gauge-ai-analyzer
AI_BACKEND=mock GAUGE_REPORT_PATH=sample_data/failed_result.json ./start.sh
```

Das Startskript legt die Python-Umgebung beim ersten Aufruf selbst an, startet
den Server und öffnet den Browser. Der erste Start dauert deshalb etwas länger.

**Windows**

```bat
git clone https://github.com/Stevenrylski/prototype-gauge-ai-analyzer.git
cd prototype-gauge-ai-analyzer\analyzer
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
set AI_BACKEND=mock
set GAUGE_REPORT_PATH=sample_data\failed_result.json
.venv\Scripts\python app.py
```

Danach im Browser öffnen: <http://127.0.0.1:5000>

> **Hinweis zu `GAUGE_REPORT_PATH`:** Gauge legt seine Reports in ein Verzeichnis,
> das per `.gitignore` bewusst nicht im Repository liegt. Die Variable zeigt
> deshalb auf einen mitgelieferten Beispiel-Report. Lässt man sie weg, erscheint
> für den ersten Workspace der Hinweis "Report nicht gefunden"; die beiden
> Demo-Workspaces sind davon nicht betroffen und funktionieren weiterhin.

## Variante B: Mit echter KI-Anbindung

Für die Anbindung an eine echte, OpenAI-kompatible API wird im Verzeichnis
`analyzer/` eine Datei namens `.env` angelegt. Als Vorlage dient die
mitgelieferte `analyzer/.env.example`.

Inhalt der Datei `analyzer/.env`:

```
AI_BACKEND=openai
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4.1-nano
OPENAI_API_KEY=<hier den separat übergebenen Schlüssel einsetzen>
```

Anschließend genügt der normale Start (ohne `AI_BACKEND=mock`):

```bash
GAUGE_REPORT_PATH=sample_data/failed_result.json ./start.sh
```

Die Oberfläche zeigt bei jeder Analyse an, welches Backend und welches Modell
verwendet wurde, sodass Mock- und KI-Antworten unterscheidbar bleiben.

**Zum API-Schlüssel:** Der Schlüssel ist ein persönliches Zugangsdatum und
liegt dieser Anleitung deshalb nicht bei, sondern wird separat übergeben. Wer
einen eigenen Schlüssel verwenden möchte, erzeugt ihn unter
<https://platform.openai.com/api-keys>. Ohne Schlüssel ist der Prototyp über
Variante A vollständig bedienbar.

## Geführter Rundgang durch die Oberfläche

1. **Gesamtsicht.** Beim Start ist der Reiter *Gesamtsicht* aktiv. Er zeigt die
   Fehlergruppen aller Workspaces zusammengeführt, sortiert nach Häufigkeit.
   Bei jeder Gruppe steht, wie oft sie auftrat und in welchen Workspaces.
2. **Wirkung der Normalisierung.** Der Workspace *demo-workspace-b* enthält 100
   fehlgeschlagene Szenarien, die zu nur zwei Gruppen zusammengefasst werden:
   99-mal derselbe Gateway-Fehler mit jeweils anderer Bestellnummer, und genau
   ein fachlich anderer Fehler. Über *Beispiele anzeigen* lassen sich die
   Originalmeldungen einer Gruppe einsehen.
3. **KI-Analyse.** *Analysieren* bei einer Gruppe liefert Klassifikation,
   Ursache, Maßnahme und eine Konfidenzangabe. Bei niedriger Konfidenz wird
   das Label farblich hervorgehoben.
4. **Caching.** Nach einer Analyse erscheint bei erneutem Aufruf der Hinweis
   *"gespeichert vom ... - nicht erneut angefragt"*. Die Analyse wird also nicht
   doppelt bezahlt. *Neu analysieren* erzwingt eine frische Anfrage.
5. **Rückfragen.** Unterhalb einer Analyse können Rückfragen gestellt werden,
   etwa *"Wie kann ich das reproduzieren?"*. Der Verlauf wird mitgespeichert.
6. **Ähnlichkeits-Check.** Der Knopf oben prüft, welche Fehlergruppen inhaltlich
   zusammengehören, auch wenn ihre Meldungen unterschiedlich formuliert sind.
7. **Transparenz.** Bei jeder Gruppe lässt sich aufklappen, was anonymisiert an
   die KI gesendet wurde.

## Optional: Eigenen Testlauf erzeugen

Ist Gauge installiert, erzeugt der folgende Aufruf zuerst einen frischen
Testlauf des beigelegten Beispielprojekts und startet danach den Analyzer:

```bash
./start.sh --tests
```

Dass dabei Tests fehlschlagen, ist beabsichtigt: Diese Fehlschläge sind die
Eingabedaten des Analyzers. In diesem Fall wird `GAUGE_REPORT_PATH` nicht
benötigt, da der Report an seinem Standardort entsteht.

## Wenn etwas nicht funktioniert

| Meldung / Symptom | Ursache und Lösung |
| --- | --- |
| `Port 5000 ist belegt` oder die Seite zeigt etwas Fremdes | Unter macOS belegt AirPlay häufig Port 5000. Mit anderem Port starten: `PORT=5050 ./start.sh` |
| `permission denied: ./start.sh` | `chmod +x start.sh` ausführen |
| `Report nicht gefunden` beim ersten Workspace | `GAUGE_REPORT_PATH` wie oben setzen oder `./start.sh --tests` verwenden |
| Analyse meldet einen Fehler der KI-API | Schlüssel, Guthaben und Netzwerkzugang prüfen. Zum Weiterarbeiten auf `AI_BACKEND=mock` wechseln |
| `command not found: python` | Unter macOS `python3` verwenden; das Startskript tut dies bereits automatisch |

## Aufbau des Repositorys

```
analyzer/                 der Prototyp
  app.py                  Flask-Server mit den JSON-Endpunkten
  report_parser.py        Report lesen, Fehler extrahieren, normalisieren, gruppieren
  ai_client.py            austauschbarer KI-Adapter (Mock oder echte API)
  anonymizer.py           Anonymisierung vor dem Senden an die KI
  analysis_store.py       persistenter Speicher für Analysen und Chatverläufe
  config.py               Einstellungen über Umgebungsvariablen
  templates/, static/     Oberfläche (HTML, CSS, JavaScript ohne Framework)
  sample_data/            Beispiel-Reports und Generator der Demo-Workspaces
sample-gauge-project/     Beispiel-Testprojekt, dient nur als Datenlieferant
start.sh                  Startskript für macOS und Linux
```

Analyzer und Testprojekt sind nur über eine einzige Datei gekoppelt, den
JSON-Report. Der Analyzer ruft Gauge nie selbst auf.
