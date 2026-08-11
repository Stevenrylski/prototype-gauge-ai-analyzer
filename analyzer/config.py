"""Zentrale Konfiguration des Prototyps.

Alle Werte lassen sich per Umgebungsvariable ueberschreiben, damit man ohne
Code-Aenderung zwischen echtem Report und Beispiel-Report bzw. zwischen Mock
und echter KI-API wechseln kann.
"""

import os
from pathlib import Path

# .env-Datei (falls vorhanden) laden, damit Geheimnisse wie der OpenAI-API-Key
# lokal in analyzer/.env stehen koennen nicht im Code und nicht in der
# Shell-History. Die .env ist via .gitignore von Git ausgeschlossen.
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass  # python-dotenv nicht installiert -> nur echte Umgebungsvariablen

# Projektwurzel = ein Verzeichnis oberhalb von analyzer/
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Pfad zum Gauge-JSON-Report. Standard: der Report des beigelegten
# Beispiel-Gauge-Projekts. Zum Entwickeln/Testen z. B. auf
# analyzer/sample_data/failed_result.json zeigen lassen.
REPORT_PATH = Path(
    os.environ.get(
        "GAUGE_REPORT_PATH",
        PROJECT_ROOT / "sample-gauge-project" / "reports" / "json-report" / "result.json",
    )
)

# ---------------------------------------------------------------------------
# Workspaces: In der Praxis gibt es viele Gauge-Projekte ("Workspaces") mit je
# einem eigenen Report. Der Analyzer liest alle ein und zeigt zusaetzlich eine
# Gesamtsicht ("Fehler X tritt in 8 von 12 Workspaces auf").
#
# Konfiguration per Umgebungsvariable GAUGE_WORKSPACES im Format
#     Name=pfad/zum/result.json;Name2=anderer/pfad/result.json
# Ohne diese Variable werden der echte Report des Beispielprojekts plus zwei
# mitgelieferte Demo-Workspace-Reports verwendet (Demonstration der Thesis).
# ---------------------------------------------------------------------------
_SAMPLE_WORKSPACE_DIR = Path(__file__).resolve().parent / "sample_data" / "workspaces"


def _parse_workspaces(raw):
    workspaces = []
    for entry in raw.split(";"):
        entry = entry.strip()
        if not entry or "=" not in entry:
            continue
        name, _, path = entry.partition("=")
        workspaces.append({"name": name.strip(), "reportPath": Path(path.strip())})
    return workspaces


_raw_workspaces = os.environ.get("GAUGE_WORKSPACES", "")
if _raw_workspaces:
    WORKSPACES = _parse_workspaces(_raw_workspaces)
else:
    WORKSPACES = [
        {"name": "sample-gauge-project", "reportPath": REPORT_PATH},
        {"name": "demo-workspace-b", "reportPath": _SAMPLE_WORKSPACE_DIR / "workspace_b.json"},
        {"name": "demo-workspace-c", "reportPath": _SAMPLE_WORKSPACE_DIR / "workspace_c.json"},
    ]

# Persistenter Speicher fuer KI-Analysen, Chatverlaeufe und Cluster-Ergebnisse
# (Schluessel = Fehler-Signatur). Liegt ausserhalb von Git (siehe .gitignore).
DATA_DIR = Path(os.environ.get("ANALYZER_DATA_DIR", Path(__file__).resolve().parent / "data"))
ANALYSIS_STORE_PATH = DATA_DIR / "analysis_store.json"

# Welcher KI-Adapter genutzt wird: "mock" (feste Beispielantwort) oder "openai"
# (selbstgehostete, OpenAI-kompatible API, z. B. Open WebUI mit Qwen3-Coder).
AI_BACKEND = os.environ.get("AI_BACKEND", "mock").lower()

# Einstellungen fuer die echte, OpenAI-kompatible API. Die Basis-URL enthaelt
# den API-Praefix (OpenAI: /v1, Open WebUI: /api) siehe OpenAICompatibleClient.
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "http://localhost:3000/api")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "qwen3-coder:30b")

# Timeout fuer den KI-Aufruf in Sekunden.
AI_TIMEOUT = float(os.environ.get("AI_TIMEOUT", "60"))
