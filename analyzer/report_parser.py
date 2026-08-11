"""Liest den Gauge-JSON-Report und extrahiert die Fehlschlaege.

Die Struktur des Reports (vereinfacht):

    specResults[]              -> Spezifikationen
      scenarios[]              -> Szenarien
        contexts[] / items[] / teardowns[]   -> Schritte ("step")
          result.status == "failed"          -> fehlgeschlagener Schritt
        beforeScenarioHookFailure / after... -> fehlgeschlagene Szenario-Hooks
      beforeSpecHookFailure / after...        -> fehlgeschlagene Spec-Hooks

Zusaetzlich koennen Schritte selbst Hook-Fehler haben
(beforeStepHookFailure / afterStepHookFailure).

Gleichartige Fehlschlaege werden zu Gruppen zusammengefasst, damit sie spaeter
nur einmal an die KI gehen. "Gleichartig" heisst dabei nicht zeichengleich:
Vor dem Vergleich werden dynamische Werte (Zahlen, IDs, Pfade, URLs,
Zeitstempel, Hex-Adressen) durch Platzhalter ersetzt (Normalisierung). So
landen z. B. 99 Fehlschlaege "Bestellung ORD-2026-0001 ... ORD-2026-0099
nicht gefunden" in EINER Gruppe - und der eine wirklich andere Fehler faellt
sofort auf.

Die normalisierte Form ergibt eine stabile Signatur (Hash), die ueber
Testlaeufe und Workspaces hinweg identisch bleibt. Sie dient als Schluessel
fuer den Analyse-Cache und fuer die workspace-uebergreifende Aggregation.
"""

import hashlib
import json
import re
from pathlib import Path

# Maximal so viele unterschiedliche Original-Meldungen werden pro Gruppe als
# Beispiel-Varianten aufgehoben (fuer die Anzeige "3 Varianten der Meldung").
MAX_VARIANTS = 5

# Normalisierungs-Muster: (Regex, Platzhalter). Reihenfolge ist wichtig
# spezifische Muster (URL, UUID, Zeitstempel) vor allgemeinen (Zahlen).
_NORMALIZE_PATTERNS = [
    (re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE), "<URL>"),
    (re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b"), "<EMAIL>"),
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}(?::\d+)?\b"), "<IP>"),
    # Windows- und Unix-Pfade (mind. zwei Segmente).
    (re.compile(r"[A-Za-z]:\\(?:[^\\\s\"']+\\)*[^\\\s\"']+"), "<PFAD>"),
    (re.compile(r"/(?:[^/\s\"']+/)+[^/\s\"']+"), "<PFAD>"),
    # UUIDs und laengere Hex-Ketten (Speicheradressen, Commit-Hashes, Tokens).
    (re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.IGNORECASE), "<ID>"),
    (re.compile(r"\b(?:0x)?[0-9a-f]{6,}\b", re.IGNORECASE), "<ID>"),
    # Zeitstempel (ISO-Datum/-Zeit) und Uhrzeiten.
    (re.compile(r"\b\d{4}-\d{2}-\d{2}[T ]?\d{0,2}:?\d{0,2}:?\d{0,2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?\b"), "<ZEIT>"),
    (re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\b"), "<ZEIT>"),
    # Zahlen (auch Dezimalzahlen) zuletzt erst danach ist z. B. aus
    # "ORD-2026-0098" ein "ORD-<N>-<N>" geworden.
    (re.compile(r"\b\d+(?:[.,]\d+)?\b"), "<N>"),
]

_WHITESPACE = re.compile(r"\s+")


def normalize_text(text):
    """Ersetzt dynamische Werte durch Platzhalter, damit gleichartige
    Fehlermeldungen trotz unterschiedlicher IDs/Zahlen vergleichbar werden."""
    if not text:
        return ""
    for pattern, placeholder in _NORMALIZE_PATTERNS:
        text = pattern.sub(placeholder, text)
    return _WHITESPACE.sub(" ", text).strip()


def load_report(path):
    """Laedt und parst die JSON-Datei. Wirft FileNotFoundError / ValueError."""
    text = Path(path).read_text(encoding="utf-8")
    return json.loads(text)


def _hook_failure_to_record(hook_failure, spec, scenario, where):
    """Wandelt ein Hook-Failure-Objekt in einen einheitlichen Fehler-Datensatz."""
    if not hook_failure:
        return None
    return {
        "kind": "hook",
        "spec": spec,
        "scenario": scenario,
        "step": where,
        "errorMessage": hook_failure.get("errorMessage", "") or "",
        "stackTrace": hook_failure.get("stackTrace", "") or "",
    }


def _step_failures(step, spec, scenario):
    """Liefert die Fehler-Datensaetze eines einzelnen Schritt-Items."""
    records = []
    step_text = step.get("stepText", "") or "(unbenannter Schritt)"

    before = _hook_failure_to_record(
        step.get("beforeStepHookFailure"), spec, scenario,
        "Before-Step-Hook: " + step_text,
    )
    if before:
        records.append(before)

    result = step.get("result") or {}
    if result.get("status") == "failed":
        records.append({
            "kind": "step",
            "spec": spec,
            "scenario": scenario,
            "step": step_text,
            "errorMessage": result.get("errorMessage", "") or "",
            "stackTrace": result.get("stackTrace", "") or "",
        })

    after = _hook_failure_to_record(
        step.get("afterStepHookFailure"), spec, scenario,
        "After-Step-Hook: " + step_text,
    )
    if after:
        records.append(after)

    return records


def extract_failures(report):
    """Geht den Report durch und sammelt alle Fehlschlaege als flache Liste."""
    failures = []

    for spec in report.get("specResults") or []:
        spec_name = spec.get("specHeading", "") or "(unbenannte Spec)"

        for record in (
            _hook_failure_to_record(spec.get("beforeSpecHookFailure"), spec_name, "", "Before-Spec-Hook"),
            _hook_failure_to_record(spec.get("afterSpecHookFailure"), spec_name, "", "After-Spec-Hook"),
        ):
            if record:
                failures.append(record)

        for scenario in spec.get("scenarios") or []:
            scen_name = scenario.get("scenarioHeading", "") or "(unbenanntes Szenario)"

            for record in (
                _hook_failure_to_record(scenario.get("beforeScenarioHookFailure"), spec_name, scen_name, "Before-Scenario-Hook"),
                _hook_failure_to_record(scenario.get("afterScenarioHookFailure"), spec_name, scen_name, "After-Scenario-Hook"),
            ):
                if record:
                    failures.append(record)

            # Schritte stehen in contexts (Setup), items (eigentliche Schritte)
            # und teardowns (Aufraeumen).
            for bucket in ("contexts", "items", "teardowns"):
                for step in scenario.get(bucket) or []:
                    if step.get("itemType") != "step":
                        continue
                    failures.extend(_step_failures(step, spec_name, scen_name))

    return failures


def signature(step, error_message):
    """Stabile Signatur einer Fehlergruppe: Hash ueber den NORMALISIERTEN
    Schritt + die NORMALISIERTE Fehlermeldung. Identisch ueber Testlaeufe und
    Workspaces hinweg, solange es "derselbe Fehler" ist auch wenn IDs,
    Betraege oder Zeitstempel variieren."""
    key = (normalize_text(step) + "\n" + normalize_text(error_message)).encode("utf-8")
    return hashlib.md5(key).hexdigest()[:12]


def group_failures(failures, workspace=""):
    """Fasst gleichartige Fehlschlaege (gleiche normalisierte Signatur)
    zusammen. ``workspace`` wird an jedem Vorkommen vermerkt, damit die
    Gruppen spaeter workspace-uebergreifend zusammengefuehrt werden koennen."""
    groups = {}
    for failure in failures:
        gid = signature(failure["step"], failure["errorMessage"])
        if gid not in groups:
            groups[gid] = {
                "id": gid,
                "kind": failure["kind"],
                "step": failure["step"],
                "errorMessage": failure["errorMessage"],
                "normalizedStep": normalize_text(failure["step"]),
                "normalizedMessage": normalize_text(failure["errorMessage"]),
                "stackTrace": failure["stackTrace"],
                "count": 0,
                "variants": [],
                # Hashes ALLER unterschiedlichen Original-Meldungen - so bleibt
                # die Varianten-Anzahl exakt, ohne 99 Meldungen zu speichern.
                "variantHashes": [],
                "occurrences": [],
                "workspaces": [workspace] if workspace else [],
            }
        group = groups[gid]
        group["count"] += 1
        message = failure["errorMessage"]
        if message:
            message_hash = hashlib.md5(message.encode("utf-8")).hexdigest()[:8]
            if message_hash not in group["variantHashes"]:
                group["variantHashes"].append(message_hash)
                if len(group["variants"]) < MAX_VARIANTS:
                    group["variants"].append(message)
        group["occurrences"].append({
            "spec": failure["spec"],
            "scenario": failure["scenario"],
            "workspace": workspace,
        })
    result = list(groups.values())
    for group in result:
        group["variantCount"] = len(group["variantHashes"])
    return result


def aggregate_groups(groups_per_workspace):
    """Fuehrt die Fehlergruppen mehrerer Workspaces zu einer Gesamtsicht
    zusammen. Gruppen mit derselben Signatur (= derselbe Fehler) werden
    verschmolzen. ``workspaces`` zeigt, in welchen Workspaces der Fehler
    auftritt (z. B. "in 8 von 12 Workspaces")."""
    merged = {}
    for groups in groups_per_workspace:
        for group in groups:
            gid = group["id"]
            if gid not in merged:
                merged[gid] = {
                    key: (list(value) if isinstance(value, list) else value)
                    for key, value in group.items()
                }
                continue
            target = merged[gid]
            target["count"] += group["count"]
            target["occurrences"].extend(group["occurrences"])
            for name in group["workspaces"]:
                if name not in target["workspaces"]:
                    target["workspaces"].append(name)
            for variant_hash, variant in zip(group["variantHashes"], group["variants"]):
                if variant_hash not in target["variantHashes"] and len(target["variants"]) < MAX_VARIANTS:
                    target["variants"].append(variant)
            for variant_hash in group["variantHashes"]:
                if variant_hash not in target["variantHashes"]:
                    target["variantHashes"].append(variant_hash)
            target["variantCount"] = len(target["variantHashes"])
    # Haeufigste Fehler zuerst so faellt "99x derselbe, 1x anders" auf.
    return sorted(merged.values(), key=lambda g: g["count"], reverse=True)


def build_summary(report, groups):
    """Kompakte Kennzahlen fuer die Kopfzeile der Weboberflaeche."""
    return {
        "projectName": report.get("projectName", ""),
        "timestamp": report.get("timestamp", ""),
        "executionStatus": report.get("executionStatus", ""),
        "successRate": report.get("successRate", 0),
        "failedSpecsCount": report.get("failedSpecsCount", 0),
        "failedScenariosCount": report.get("failedScenariosCount", 0),
        "failureGroupCount": len(groups),
        "totalFailures": sum(g["count"] for g in groups),
    }
