"""Persistenter Speicher fuer KI-Analysen, Chatverlaeufe und Cluster-Ergebnisse.

Kernidee "nicht immer erneut analysieren": Jede Analyse wird unter der
normalisierten Fehler-Signatur (siehe report_parser.signature) auf Platte
abgelegt. Taucht derselbe Fehler im naechsten Testlauf oder in einem anderen
Workspace wieder auf, wird die gespeicherte Analyse angezeigt statt die KI
erneut zu fragen. Ein "Neu analysieren"-Knopf im Frontend erzwingt bei Bedarf
eine frische Analyse (z. B. nach einer Code-Aenderung).

Format der JSON-Datei:

    {
      "analyses": {
        "<signatur>": {
          "analysis": {               strukturierte KI-Antwort der Erst-Analyse
            "klassifikation": "...", "ursache": "...",
            "massnahme": "...", "konfidenz": "hoch"|"mittel"|"niedrig"
          },
          "sentToAI": "...",          anonymisierter Prompt (Transparenz, NFA#4)
          "backend": "mock"|"openai",
          "model": "...",             Modellname ("" im Mock-Betrieb)
          "analyzedAt": "2026-07-15T10:00:00",
          "chat": [ {"role": "user"|"assistant", "content": "..."}, ... ]
        }
      },
      "clusters": {
        "<hash der Signatur-Menge>": { "clusters": [...], "createdAt": "..." }
      }
    }

Einfache JSON-Datei statt Datenbank fuer den Prototyp ausreichend und in
der Thesis leicht nachvollziehbar. Ein Lock schuetzt vor parallelen Requests.
"""

import json
import threading
from datetime import datetime
from pathlib import Path

import config

_lock = threading.Lock()


def _empty():
    return {"analyses": {}, "clusters": {}}


def _load():
    try:
        text = Path(config.ANALYSIS_STORE_PATH).read_text(encoding="utf-8")
        data = json.loads(text)
    except (FileNotFoundError, ValueError):
        return _empty()
    if not isinstance(data, dict):
        return _empty()
    data.setdefault("analyses", {})
    data.setdefault("clusters", {})
    return data


def _save(data):
    path = Path(config.ANALYSIS_STORE_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_analysis(signature):
    """Gespeicherter Eintrag zu einer Fehler-Signatur oder None.

    Eintraege im alten Textformat (analysis als String statt Dict) gelten
    als Cache-Miss und werden beim naechsten Analysieren ueberschrieben
    einfacher, als zwei Anzeigeformate zu pflegen. Ein vorhandener
    Chatverlauf bleibt dabei erhalten (siehe save_analysis)."""
    with _lock:
        entry = _load()["analyses"].get(signature)
    if entry and not isinstance(entry.get("analysis"), dict):
        return None
    return entry


def save_analysis(signature, analysis, sent_to_ai, backend, model=""):
    """Legt eine (neue) Analyse ab. Ein vorhandener Chatverlauf bleibt bei
    einer erzwungenen Neu-Analyse erhalten."""
    with _lock:
        data = _load()
        previous = data["analyses"].get(signature) or {}
        entry = {
            "analysis": analysis,
            "sentToAI": sent_to_ai,
            "backend": backend,
            "model": model,
            "analyzedAt": datetime.now().isoformat(timespec="seconds"),
            "chat": previous.get("chat", []),
        }
        data["analyses"][signature] = entry
        _save(data)
        return entry


def append_chat(signature, user_message, assistant_message):
    """Haengt ein Frage/Antwort-Paar an den Chatverlauf einer Analyse an."""
    with _lock:
        data = _load()
        entry = data["analyses"].get(signature)
        if entry is None:
            raise KeyError("Keine Analyse zu dieser Signatur gespeichert.")
        entry.setdefault("chat", []).extend([
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": assistant_message},
        ])
        _save(data)
        return entry


def analysis_meta(signatures):
    """Kompakte Cache-Infos fuer eine Menge von Signaturen fuers Frontend
    ("Analyse vorhanden vom ...", Anzahl Chat-Nachrichten)."""
    with _lock:
        analyses = _load()["analyses"]
    meta = {}
    for sig in signatures:
        entry = analyses.get(sig)
        # Altformat-Eintraege (analysis als String) zaehlen nicht als
        # vorhandene Analyse konsistent zum Cache-Miss in get_analysis.
        if entry and isinstance(entry.get("analysis"), dict):
            meta[sig] = {
                "analyzedAt": entry.get("analyzedAt", ""),
                "backend": entry.get("backend", ""),
                "model": entry.get("model", ""),
                "chatLength": len(entry.get("chat", [])),
            }
    return meta


def get_cluster(key):
    """Gespeichertes Cluster-Ergebnis fuer eine Signatur-Menge oder None."""
    with _lock:
        return _load()["clusters"].get(key)


def save_cluster(key, clusters, backend):
    with _lock:
        data = _load()
        entry = {
            "clusters": clusters,
            "backend": backend,
            "createdAt": datetime.now().isoformat(timespec="seconds"),
        }
        data["clusters"][key] = entry
        _save(data)
        return entry
