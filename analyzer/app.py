"""Flask-Backend des Prototyps.

Routen:
    GET  /              -> Weboberflaeche
    GET  /api/report    -> Kennzahlen + gruppierte Fehlschlaege aus dem Report
    POST /api/analyze   -> einen Fehler anonymisieren und von der KI analysieren
"""

from flask import Flask, jsonify, render_template, request

import config
from ai_client import AIClientError, build_prompt, get_ai_client
from anonymizer import anonymize
from report_parser import (
    build_summary,
    extract_failures,
    group_failures,
    load_report,
)

app = Flask(__name__)


def _load_groups():
    """Liest den Report und liefert (summary, groups). Wirft bei Lesefehlern."""
    report = load_report(config.REPORT_PATH)
    failures = extract_failures(report)
    groups = group_failures(failures)
    summary = build_summary(report, groups)
    return summary, groups


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/report")
def api_report():
    try:
        summary, groups = _load_groups()
    except FileNotFoundError:
        return jsonify({
            "error": "Report nicht gefunden: " + str(config.REPORT_PATH)
                     + ". Bitte zuerst einen Gauge-Lauf ausfuehren."
        }), 404
    except ValueError:
        return jsonify({"error": "Der Report ist kein gueltiges JSON."}), 400
    return jsonify({"summary": summary, "groups": groups})


@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    data = request.get_json(silent=True) or {}
    group_id = data.get("id")
    if not group_id:
        return jsonify({"error": "Es wurde keine Fehler-ID uebergeben."}), 400

    try:
        _, groups = _load_groups()
    except FileNotFoundError:
        return jsonify({"error": "Report nicht gefunden."}), 404
    except ValueError:
        return jsonify({"error": "Der Report ist kein gueltiges JSON."}), 400

    group = next((g for g in groups if g["id"] == group_id), None)
    if group is None:
        return jsonify({"error": "Fehler-ID nicht im aktuellen Report gefunden."}), 404

    # DSGVO: Prompt aus dem Fehler bauen und als Ganzes anonymisieren. So wird
    # ein z. B. nur im Stacktrace erkannter Benutzername auch in der
    # Fehlermeldung ersetzt. Den gesendeten Text geben wir transparent zurueck,
    # damit im Frontend sichtbar ist, was die KI tatsaechlich erhaelt.
    prompt = anonymize(build_prompt(group))

    try:
        analysis = get_ai_client().analyze(prompt)
    except AIClientError as exc:
        return jsonify({"error": str(exc)}), 502
    except Exception:  # pragma: no cover - Sicherheitsnetz fuer den Prototyp
        return jsonify({"error": "Unerwarteter Fehler bei der KI-Analyse."}), 500

    return jsonify({
        "id": group_id,
        "analysis": analysis,
        "sentToAI": prompt,
        "backend": config.AI_BACKEND,
    })


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
