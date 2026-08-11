# prototype-gauge-ai-analyzer

> **Bachelor-Thesis-Prototyp (Steven Rylski, 2026)** - KI-gestützte Auswertung von
> Gauge-Testergebnissen. Proof of Concept, **kein Produktivsystem**.

Fehlgeschlagene Tests aus [Gauge](https://gauge.org) werden automatisch von einer
KI analysiert (wahrscheinliche Ursache + Lösungshinweis) und in einer schlichten
Weboberfläche angezeigt.

## Pipeline

```
Gauge-Testläufe (mehrere Workspaces) -> JSON-Reports -> Backend liest & extrahiert
-> Normalisierung (dynamische Werte maskieren) -> Gruppierung nach Fehler-Signatur
-> Anonymisierung (DSGVO) -> Prompt -> KI-API -> Analyse -> persistenter Cache
-> Anzeige im Browser (Gesamtsicht + pro Workspace, Chat, Ähnlichkeits-Check)
```

## Kernfunktionen

* **Normalisierte Fehlergruppierung** - dynamische Werte (Bestellnummern,
  Beträge, Zeitstempel, Speicheradressen ...) werden maskiert, bevor Fehler
  verglichen werden. 99 Fehlschläge mit unterschiedlichen IDs, aber gleichem
  Muster, ergeben **eine** Gruppe - der eine wirklich andere Fehler fällt auf.
* **Multi-Workspace-Gesamtsicht** - mehrere Gauge-Reports werden eingelesen
  (Umgebungsvariable `GAUGE_WORKSPACES=Name=pfad;Name2=pfad`). Die Gesamtsicht
  zeigt pro Fehler "tritt in X von Y Workspaces auf". Ohne Konfiguration werden
  das Beispielprojekt plus zwei generierte Demo-Workspaces geladen
  (`analyzer/sample_data/generate_workspaces.py`).
* **Persistenter Analyse-Cache** - jede KI-Analyse wird unter der
  Fehler-Signatur in `analyzer/data/analysis_store.json` gespeichert. Derselbe
  Fehler wird auch nach Neustart oder im nächsten Testlauf **nicht erneut**
  an die KI geschickt "Neu analysieren" erzwingt eine frische Analyse.
* **Chat pro Fehlergruppe** - nach der Erst-Analyse können Rückfragen gestellt
  werden ("Wie reproduziere ich das?"). Der Verlauf wird mitpersistiert und
  ebenfalls anonymisiert.
* **KI-Ähnlichkeits-Check** - auf Knopfdruck prüft die KI, welche
  Fehlergruppen vermutlich dieselbe Ursache haben (z. B. Bezahl-Gateway-Ausfall
  und Datenbank-Hook-Fehler = derselbe nicht erreichbare Dienst).

## Aufbau

```
prototype-gauge-ai-analyzer/
├─ analyzer/               <- der Prototyp (Backend + Frontend) - der eigentliche Beitrag
│  ├─ app.py               Flask-Server (Routen)
│  ├─ report_parser.py     Report lesen, Fehler extrahieren + gruppieren
│  ├─ anonymizer.py        DSGVO-Anonymisierung vor dem Senden an die KI
│  ├─ ai_client.py         austauschbarer KI-Adapter (Mock <-> echte API)
│  ├─ config.py            Einstellungen (Report-Pfad, KI-Backend)
│  ├─ requirements.txt     flask, requests
│  ├─ templates/, static/  HTML / CSS / Vanilla-JS (kein Framework, kein Build)
│  └─ sample_data/         fehlschlagender Beispiel-Report zum Testen
└─ sample-gauge-project/   <- Beispiel-Gauge-Projekt, dient nur als Datenlieferant
   ├─ specs/, step_impl/    die Beispiel-Tests
   └─ reports/json-report/result.json   der erzeugte Report (Eingabe des Analyzers)
```

`analyzer/` und `sample-gauge-project/` sind **nur über eine Datei gekoppelt**:
den JSON-Report. Der Analyzer kennt Gauge nicht - er liest ausschließlich
`result.json`.

## Starten

**1. (Optional) Testdaten erzeugen** - einen fehlschlagenden Gauge-Lauf:

```bash
cd sample-gauge-project
gauge run specs        # erzeugt reports/json-report/result.json
```

**2. Analyzer starten:**

```bash
cd analyzer
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt    # Windows (Git Bash: Schrägstriche!)
.venv/Scripts/python app.py
```

Dann im Browser öffnen: <http://127.0.0.1:5000>

Ohne eigenen Gauge-Lauf kann der Analyzer auch direkt den beigelegten
Beispiel-Report verwenden:

```bash
GAUGE_REPORT_PATH=sample_data/failed_result.json .venv/Scripts/python app.py
```

## KI-Anbindung (Mock <-> echte API)

Standardmäßig liefert ein **Mock** eine feste Beispielantwort - es wird keine
echte KI kontaktiert. Auf eine echte, OpenAI-kompatible API umschalten - ohne
Code-Änderung, nur über Umgebungsvariablen (oder `analyzer/.env`, siehe
`analyzer/.env.example`):

```bash
AI_BACKEND=openai \
OPENAI_BASE_URL=http://<open-webui-host>/api \
OPENAI_API_KEY=<key> \
OPENAI_MODEL=qwen3-coder:30b \
.venv/Scripts/python app.py
```

Die Basis-URL enthält den API-Präfix des Anbieters, der Client hängt nur noch
`/chat/completions` an: Open WebUI -> `http://<host>/api` (kein `/v1`!),
echtes OpenAI -> `https://api.openai.com/v1`. Den Open-WebUI-Key erzeugt man
unter *Einstellungen -> Konto -> API-Schlüssel*.

## DSGVO

Vor dem Senden an die KI werden Pfade, Benutzernamen, Hostnames/URLs, E-Mails
und IP-Adressen ersetzt (`anonymizer.py`). Die Weboberfläche zeigt unter
"An die KI gesendet (anonymisiert)" transparent, was tatsächlich übermittelt wird.
