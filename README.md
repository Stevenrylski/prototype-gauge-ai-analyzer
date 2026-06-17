# prototype-gauge-ai-analyzer

> **Bachelor-Thesis-Prototyp (Steven Rylski, 2026)** – KI-gestützte Auswertung von
> Gauge-Testergebnissen. Proof of Concept, **kein Produktivsystem**.

Fehlgeschlagene Tests aus [Gauge](https://gauge.org) werden automatisch von einer
KI analysiert (wahrscheinliche Ursache + Lösungshinweis) und in einer schlichten
Weboberfläche angezeigt.

## Pipeline

```
Gauge-Testlauf → JSON-Report → Backend liest & extrahiert Fehlschläge
→ Anonymisierung (DSGVO) → Prompt → KI-API → Analyse → Anzeige im Browser
```

## Aufbau

```
prototype-gauge-ai-analyzer/
├─ analyzer/               ← der Prototyp (Backend + Frontend) – der eigentliche Beitrag
│  ├─ app.py               Flask-Server (Routen)
│  ├─ report_parser.py     Report lesen, Fehler extrahieren + gruppieren
│  ├─ anonymizer.py        DSGVO-Anonymisierung vor dem Senden an die KI
│  ├─ ai_client.py         austauschbarer KI-Adapter (Mock ↔ echte API)
│  ├─ config.py            Einstellungen (Report-Pfad, KI-Backend)
│  ├─ requirements.txt     flask, requests
│  ├─ templates/, static/  HTML / CSS / Vanilla-JS (kein Framework, kein Build)
│  └─ sample_data/         fehlschlagender Beispiel-Report zum Testen
└─ sample-gauge-project/   ← Beispiel-Gauge-Projekt, dient nur als Datenlieferant
   ├─ specs/, step_impl/    die Beispiel-Tests
   └─ reports/json-report/result.json   der erzeugte Report (Eingabe des Analyzers)
```

`analyzer/` und `sample-gauge-project/` sind **nur über eine Datei gekoppelt**:
den JSON-Report. Der Analyzer kennt Gauge nicht – er liest ausschließlich
`result.json`.

## Starten

**1. (Optional) Testdaten erzeugen** – einen fehlschlagenden Gauge-Lauf:

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

## KI-Anbindung (Mock ↔ echte API)

Standardmäßig liefert ein **Mock** eine feste Beispielantwort – es wird keine
echte KI kontaktiert (die Ziel-Infrastruktur, Open WebUI mit Qwen3-Coder, ist
noch nicht erreichbar). Auf die echte, OpenAI-kompatible API umschalten – ohne
Code-Änderung, nur über Umgebungsvariablen:

```bash
AI_BACKEND=openai \
OPENAI_BASE_URL=http://<open-webui-host>/api \
OPENAI_API_KEY=<key> \
OPENAI_MODEL=qwen3-coder:30b \
.venv/Scripts/python app.py
```

## DSGVO

Vor dem Senden an die KI werden Pfade, Benutzernamen, Hostnames/URLs, E-Mails
und IP-Adressen ersetzt (`anonymizer.py`). Die Weboberfläche zeigt unter
„An die KI gesendet (anonymisiert)" transparent, was tatsächlich übermittelt wird.
