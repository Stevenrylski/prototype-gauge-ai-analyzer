"""Zentrale Konfiguration des Prototyps.

Alle Werte lassen sich per Umgebungsvariable ueberschreiben, damit man ohne
Code-Aenderung zwischen echtem Report und Beispiel-Report bzw. zwischen Mock
und echter KI-API wechseln kann.
"""

import os
from pathlib import Path

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

# Welcher KI-Adapter genutzt wird: "mock" (feste Beispielantwort) oder "openai"
# (selbstgehostete, OpenAI-kompatible API, z. B. Open WebUI mit Qwen3-Coder).
AI_BACKEND = os.environ.get("AI_BACKEND", "mock").lower()

# Einstellungen fuer die echte, OpenAI-kompatible API.
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "http://localhost:3000/api")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "qwen3-coder:30b")

# Timeout fuer den KI-Aufruf in Sekunden.
AI_TIMEOUT = float(os.environ.get("AI_TIMEOUT", "60"))
