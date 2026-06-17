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

Identische Fehlschlaege (gleicher Schritt + gleiche Fehlermeldung) werden zu
Gruppen zusammengefasst, damit sie spaeter nur einmal an die KI gehen.
"""

import hashlib
import json
from pathlib import Path


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


def _group_id(step, error_message):
    """Stabile, kurze ID fuer eine Fehlergruppe (deterministisch ueber Requests)."""
    key = (step + "\n" + error_message).encode("utf-8")
    return hashlib.md5(key).hexdigest()[:8]


def group_failures(failures):
    """Fasst identische Fehlschlaege (gleicher Schritt + gleiche Meldung) zusammen."""
    groups = {}
    for failure in failures:
        gid = _group_id(failure["step"], failure["errorMessage"])
        if gid not in groups:
            groups[gid] = {
                "id": gid,
                "kind": failure["kind"],
                "step": failure["step"],
                "errorMessage": failure["errorMessage"],
                "stackTrace": failure["stackTrace"],
                "count": 0,
                "occurrences": [],
            }
        groups[gid]["count"] += 1
        groups[gid]["occurrences"].append({
            "spec": failure["spec"],
            "scenario": failure["scenario"],
        })
    return list(groups.values())


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
