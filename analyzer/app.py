"""Flask-Backend des Prototyps.

Routen:
    GET  /              -> Weboberflaeche
    GET  /api/report    -> alle Workspaces + workspace-uebergreifende Gesamtsicht
    POST /api/analyze   -> Fehler analysieren (mit persistentem Cache, force=neu)
    POST /api/chat      -> Rueckfrage zu einem bereits analysierten Fehler
    POST /api/cluster   -> KI-Aehnlichkeits-Check ueber alle Fehlergruppen
"""

import hashlib
import os

from flask import Flask, jsonify, render_template, request

import analysis_store
import config
from ai_client import (
    AIClientError,
    CHAT_SYSTEM_PROMPT,
    build_prompt,
    get_ai_client,
)
from anonymizer import anonymize
from report_parser import (
    aggregate_groups,
    build_summary,
    extract_failures,
    group_failures,
    load_report,
)

app = Flask(__name__)


def _load_workspaces():
    """Laedt die Reports aller konfigurierten Workspaces.

    Liefert (workspaces, aggregate):
      workspaces: Liste je Workspace bei Erfolg mit summary + groups,
                  bei Lesefehlern mit einer Fehlermeldung (die uebrigen
                  Workspaces bleiben nutzbar).
      aggregate:  ueber alle geladenen Workspaces zusammengefuehrte Gruppen.
    """
    workspaces = []
    groups_per_workspace = []

    for entry in config.WORKSPACES:
        name = entry["name"]
        try:
            report = load_report(entry["reportPath"])
        except FileNotFoundError:
            workspaces.append({
                "name": name,
                "error": "Report nicht gefunden: " + str(entry["reportPath"]),
            })
            continue
        except ValueError:
            workspaces.append({
                "name": name,
                "error": "Der Report ist kein gueltiges JSON: " + str(entry["reportPath"]),
            })
            continue

        failures = extract_failures(report)
        groups = group_failures(failures, workspace=name)
        groups_per_workspace.append(groups)
        workspaces.append({
            "name": name,
            "summary": build_summary(report, groups),
            "groups": groups,
        })

    aggregate = aggregate_groups(groups_per_workspace)
    return workspaces, aggregate


def _attach_cache_meta(groups):
    """Ergaenzt jede Gruppe um Infos zur gespeicherten Analyse (falls vorhanden)."""
    meta = analysis_store.analysis_meta([g["id"] for g in groups])
    for group in groups:
        group["analysisMeta"] = meta.get(group["id"])


def _find_group(group_id):
    """Sucht eine Fehlergruppe per Signatur in der Gesamtsicht."""
    _, aggregate = _load_workspaces()
    return next((g for g in aggregate if g["id"] == group_id), None)


def _current_model():
    """Modellname des aktiven Backends (fuer die Persistenz, NFA#4)."""
    return config.OPENAI_MODEL if config.AI_BACKEND == "openai" else ""


def _analysis_as_text(analysis):
    """Strukturierte Analyse als lesbaren Text fuer den Chat-Kontext."""
    return ("Wahrscheinliche Ursache: " + analysis.get("ursache", "") + "\n"
            "Massnahme: " + analysis.get("massnahme", ""))


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/report")
def api_report():
    workspaces, aggregate = _load_workspaces()

    loaded = [w for w in workspaces if "groups" in w]
    if not loaded:
        return jsonify({
            "error": "Kein Workspace-Report konnte geladen werden. Bitte zuerst "
                     "einen Gauge-Lauf ausfuehren oder GAUGE_WORKSPACES pruefen.",
            "workspaces": workspaces,
        }), 404

    _attach_cache_meta(aggregate)
    for workspace in loaded:
        _attach_cache_meta(workspace["groups"])

    aggregate_summary = {
        "workspaceCount": len(workspaces),
        "loadedWorkspaceCount": len(loaded),
        "failureGroupCount": len(aggregate),
        "totalFailures": sum(g["count"] for g in aggregate),
    }
    return jsonify({
        "workspaces": workspaces,
        "aggregate": {"summary": aggregate_summary, "groups": aggregate},
        "backend": config.AI_BACKEND,
    })


@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    data = request.get_json(silent=True) or {}
    group_id = data.get("id")
    force = bool(data.get("force"))
    if not group_id:
        return jsonify({"error": "Es wurde keine Fehler-ID uebergeben."}), 400

    group = _find_group(group_id)
    if group is None:
        return jsonify({"error": "Fehler-ID nicht im aktuellen Report gefunden."}), 404

    # Persistenter Cache: Dieselbe Fehler-Signatur wird nicht erneut an die
    # KI geschickt auch nicht nach einem Neustart oder im naechsten
    # Testlauf. "force" (Neu analysieren) umgeht den Cache gezielt.
    if not force:
        cached = analysis_store.get_analysis(group_id)
        if cached:
            return jsonify({
                "id": group_id,
                "analysis": cached["analysis"],
                "sentToAI": cached.get("sentToAI", ""),
                "backend": cached.get("backend", config.AI_BACKEND),
                "model": cached.get("model", ""),
                "analyzedAt": cached.get("analyzedAt", ""),
                "chat": cached.get("chat", []),
                "cached": True,
            })

    # DSGVO: Prompt aus dem Fehler bauen und als Ganzes anonymisieren. So wird
    # ein z. B. nur im Stacktrace erkannter Benutzername auch in der
    # Fehlermeldung ersetzt. Den gesendeten Text geben wir transparent zurueck,
    # damit im Frontend sichtbar ist, was die KI tatsaechlich erhaelt.
    prompt = anonymize(build_prompt(group))

    try:
        analysis = get_ai_client().analyze(prompt)
    except AIClientError as exc:
        return jsonify({"error": str(exc)}), 502
    except Exception:  # pragma: no cover Sicherheitsnetz fuer den Prototyp
        return jsonify({"error": "Unerwarteter Fehler bei der KI-Analyse."}), 500

    entry = analysis_store.save_analysis(
        group_id, analysis, prompt, config.AI_BACKEND, _current_model()
    )
    return jsonify({
        "id": group_id,
        "analysis": analysis,
        "sentToAI": prompt,
        "backend": config.AI_BACKEND,
        "model": entry.get("model", ""),
        "analyzedAt": entry["analyzedAt"],
        "chat": entry.get("chat", []),
        "cached": False,
    })


@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.get_json(silent=True) or {}
    group_id = data.get("id")
    message = (data.get("message") or "").strip()
    if not group_id:
        return jsonify({"error": "Es wurde keine Fehler-ID uebergeben."}), 400
    if not message:
        return jsonify({"error": "Die Nachricht ist leer."}), 400

    entry = analysis_store.get_analysis(group_id)
    if entry is None:
        return jsonify({"error": "Bitte zuerst die KI-Analyse ausfuehren, "
                                 "dann sind Rueckfragen moeglich."}), 409

    group = _find_group(group_id)
    if group is None:
        return jsonify({"error": "Fehler-ID nicht im aktuellen Report gefunden."}), 404

    # Gespraechskontext: Fehlerdetails + Erst-Analyse + bisheriger Verlauf +
    # neue Frage. Auch die Nutzerfrage wird anonymisiert, falls sie z. B.
    # einen Hostnamen enthaelt.
    user_message = anonymize(message)
    messages = [
        {"role": "system", "content": CHAT_SYSTEM_PROMPT},
        {"role": "user", "content": entry.get("sentToAI") or anonymize(build_prompt(group))},
        {"role": "assistant", "content": _analysis_as_text(entry["analysis"])},
    ]
    messages.extend(entry.get("chat", []))
    messages.append({"role": "user", "content": user_message})

    try:
        reply = get_ai_client().chat(messages)
    except AIClientError as exc:
        return jsonify({"error": str(exc)}), 502
    except Exception:  # pragma: no cover Sicherheitsnetz fuer den Prototyp
        return jsonify({"error": "Unerwarteter Fehler bei der KI-Anfrage."}), 500

    entry = analysis_store.append_chat(group_id, user_message, reply)
    return jsonify({
        "id": group_id,
        "reply": reply,
        "chat": entry["chat"],
        "backend": config.AI_BACKEND,
    })


@app.route("/api/cluster", methods=["POST"])
def api_cluster():
    data = request.get_json(silent=True) or {}
    force = bool(data.get("force"))

    _, aggregate = _load_workspaces()
    if len(aggregate) < 2:
        return jsonify({"clusters": [], "cached": False,
                        "note": "Weniger als zwei Fehlergruppen nichts zu vergleichen."})

    # Cache-Schluessel = Hash der Signatur-Menge: Solange dieselben
    # Fehlergruppen vorliegen, wird der Aehnlichkeits-Check nicht wiederholt.
    key = hashlib.md5("\n".join(sorted(g["id"] for g in aggregate)).encode("utf-8")).hexdigest()[:12]
    if not force:
        cached = analysis_store.get_cluster(key)
        if cached:
            return jsonify({
                "clusters": cached["clusters"],
                "backend": cached.get("backend", config.AI_BACKEND),
                "createdAt": cached.get("createdAt", ""),
                "cached": True,
            })

    # Nur anonymisierte, normalisierte Daten an die KI geben.
    payload = [{
        "id": g["id"],
        "step": anonymize(g["step"]),
        "normalizedMessage": anonymize(g["normalizedMessage"]),
    } for g in aggregate]

    try:
        clusters = get_ai_client().cluster(payload)
    except AIClientError as exc:
        return jsonify({"error": str(exc)}), 502
    except Exception:  # pragma: no cover Sicherheitsnetz fuer den Prototyp
        return jsonify({"error": "Unerwarteter Fehler beim Aehnlichkeits-Check."}), 500

    entry = analysis_store.save_cluster(key, clusters, config.AI_BACKEND)
    return jsonify({
        "clusters": clusters,
        "backend": config.AI_BACKEND,
        "createdAt": entry["createdAt"],
        "cached": False,
    })


if __name__ == "__main__":
    # PORT per Umgebungsvariable, da Port 5000 auf macOS oft von AirPlay
    # belegt ist.
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")), debug=True)
