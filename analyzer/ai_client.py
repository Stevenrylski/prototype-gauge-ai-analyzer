"""KI-Anbindung hinter einem austauschbaren Adapter.

Die Flask-Routen kennen nur drei Methoden des Adapters:

    analyze(prompt)   -> Erst-Analyse eines Fehlers als validiertes Dict
                         (klassifikation, ursache, massnahme, konfidenz)
    chat(messages)    -> Rueckfragen-Dialog zu einem Fehler (Chatverlauf)
    cluster(groups)   -> "Welche Fehlergruppen sind vermutlich dieselbe Ursache?"

Welcher konkrete Dienst dahinter steckt (Mock oder echte, OpenAI-kompatible
API), entscheidet ``get_ai_client()`` anhand der Konfiguration. So laesst sich
der KI-Dienst austauschen, ohne den restlichen Code anzufassen.
"""

import json
import re

import requests

import config


class AIClientError(Exception):
    """Fehler beim KI-Aufruf (Ausfall, Timeout, ungueltige Antwort)."""


# Vier-Block-Schema wie beim Cluster-Prompt: Rolle/Kontext -> Aufgabe ->
# Vorgehen (Zero-Shot-CoT) -> Formatvorgabe mit Wiederholung der Kernanweisung.
SYSTEM_PROMPT = (
    "Du bist ein Assistent, der fehlgeschlagene automatisierte Tests (Gauge) "
    "analysiert. Du erhaeltst Schritt, Fehlermeldung und Stacktrace eines "
    "Fehlschlags.\n"
    "Ordne den Fehler einer kurzen Kategorie zu (z. B. Infrastrukturproblem, "
    "Testdatenproblem, Programmfehler, Testfehler), formuliere eine "
    "verstaendliche Ursachenhypothese und schlage eine konkrete Massnahme "
    "als naechsten Schritt vor.\n"
    "Denke zuerst Schritt fuer Schritt ueber den Fehler nach. Gib danach als "
    "letzten Block deiner Antwort AUSSCHLIESSLICH ein JSON-Objekt aus nur "
    "dieses JSON wird ausgewertet, der Ueberlegungstext davor nicht.\n"
    "Das JSON-Objekt hat genau diese vier Felder, alle Werte auf Deutsch:\n"
    '{"klassifikation": "<kurze Fehlerkategorie>", '
    '"ursache": "<verstaendliche Ursachenhypothese>", '
    '"massnahme": "<konkreter Loesungshinweis>", '
    '"konfidenz": "hoch" | "mittel" | "niedrig"}\n'
    "Nach dem JSON-Objekt darf nichts mehr folgen."
)

CHAT_SYSTEM_PROMPT = (
    "Du bist ein Assistent, der fehlgeschlagene automatisierte Tests (Gauge) "
    "analysiert. Der Nutzer stellt Rueckfragen zu einem konkreten Testfehler, "
    "dessen Details und deine bisherige Analyse im Verlauf stehen. Antworte "
    "auf Deutsch, knapp und konkret, und bleibe beim Kontext dieses Fehlers."
)

CLUSTER_SYSTEM_PROMPT = (
    "Du bist ein Assistent, der Fehlergruppen aus automatisierten Testlaeufen "
    "vergleicht. Du erhaeltst eine Liste von Fehlergruppen (id, Schritt, "
    "normalisierte Fehlermeldung). Finde Gruppen, die vermutlich DIESELBE "
    "Ursache haben (z. B. derselbe ausgefallene Dienst hinter verschiedenen "
    "Meldungen). Antworte AUSSCHLIESSLICH mit JSON in genau diesem Format, "
    "ohne Erklaertext davor oder danach:\n"
    '{"clusters": [{"ids": ["id1", "id2"], "reason": "kurze Begruendung"}]}\n'
    "Nimm nur Cluster mit mindestens zwei Gruppen auf. Findest du keine, "
    'antworte mit {"clusters": []}.'
)


def build_prompt(failure):
    """Baut den Nutzer-Prompt aus einem (bereits anonymisierten) Fehler-Datensatz."""
    parts = [
        "Ein automatisierter Test ist fehlgeschlagen.",
        "",
        "Schritt: " + (failure.get("step") or "(unbekannt)"),
        "Fehlermeldung: " + (failure.get("errorMessage") or "(keine)"),
    ]
    count = failure.get("count") or 0
    if count > 1:
        parts.append(
            "Hinweis: Dieser Fehler ist im Lauf " + str(count)
            + "x mit gleichem Muster aufgetreten (dynamische Werte wie IDs "
            "koennen variieren)."
        )
    stack = failure.get("stackTrace")
    if stack:
        parts += ["", "Stacktrace:", stack]
    return "\n".join(parts)


def build_cluster_prompt(groups):
    """Baut den Nutzer-Prompt fuer den Aehnlichkeits-Check aus (bereits
    anonymisierten) Fehlergruppen."""
    lines = [
        "Hier sind die Fehlergruppen des aktuellen Testlaufs. Welche davon "
        "haben vermutlich dieselbe Ursache?",
        "",
    ]
    for group in groups:
        lines.append("- id: " + group["id"])
        lines.append("  Schritt: " + (group.get("step") or "(unbekannt)"))
        lines.append("  Fehlermeldung: " + (group.get("normalizedMessage") or "(keine)"))
    return "\n".join(lines)


# Pflichtfelder der strukturierten Analyse und erlaubte Konfidenz-Werte.
ANALYSIS_FIELDS = ("klassifikation", "ursache", "massnahme", "konfidenz")
KONFIDENZ_WERTE = ("hoch", "mittel", "niedrig")


def parse_analysis_response(text):
    """Extrahiert das LETZTE JSON-Objekt aus einer (KI-)Antwort und validiert
    die vier Analyse-Felder. Der Ueberlegungstext davor (Zero-Shot-CoT) wird
    verworfen - verwertet wird nur das JSON."""
    matches = re.findall(r"\{[^{}]*\}", text or "", re.DOTALL)
    if not matches:
        raise AIClientError("Die KI-Antwort zur Analyse enthielt kein JSON-Objekt.")
    try:
        data = json.loads(matches[-1])
    except ValueError as exc:
        raise AIClientError("Die KI-Antwort zur Analyse war kein gueltiges JSON.") from exc
    analysis = {}
    for field in ANALYSIS_FIELDS:
        value = str(data.get(field) or "").strip()
        if not value:
            raise AIClientError(
                'In der KI-Antwort fehlt das Feld "' + field + '" oder es ist leer.'
            )
        analysis[field] = value
    if analysis["konfidenz"] not in KONFIDENZ_WERTE:
        raise AIClientError(
            'Das Feld "konfidenz" der KI-Antwort muss "hoch", "mittel" oder '
            '"niedrig" sein, war aber: ' + analysis["konfidenz"]
        )
    return analysis


def parse_cluster_response(text):
    """Extrahiert das JSON-Objekt aus einer (KI-)Antwort und validiert es."""
    match = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not match:
        raise AIClientError("Die KI-Antwort zum Aehnlichkeits-Check enthielt kein JSON.")
    try:
        data = json.loads(match.group(0))
    except ValueError as exc:
        raise AIClientError("Die KI-Antwort zum Aehnlichkeits-Check war kein gueltiges JSON.") from exc
    clusters = data.get("clusters")
    if not isinstance(clusters, list):
        raise AIClientError("Die KI-Antwort zum Aehnlichkeits-Check hatte ein unerwartetes Format.")
    cleaned = []
    for cluster in clusters:
        ids = cluster.get("ids") if isinstance(cluster, dict) else None
        if isinstance(ids, list) and len(ids) >= 2:
            cleaned.append({
                "ids": [str(i) for i in ids],
                "reason": str(cluster.get("reason", "")),
            })
    return cleaned


class AIClient:
    """Schnittstelle, die jeder konkrete KI-Adapter implementiert."""

    def analyze(self, prompt):
        """Erst-Analyse eines Fehlers. Liefert ein validiertes Dict mit den
        Feldern klassifikation, ursache, massnahme, konfidenz."""
        raise NotImplementedError

    def chat(self, messages):
        """Fuehrt einen Rueckfragen-Dialog fort. ``messages`` ist eine Liste
        von {"role": ..., "content": ...} inkl. System-Prompt."""
        raise NotImplementedError

    def cluster(self, groups):
        """Findet Fehlergruppen mit vermutlich derselben Ursache. Liefert
        eine Liste von {"ids": [...], "reason": "..."}."""
        raise NotImplementedError


class MockAIClient(AIClient):
    """Regelbasierte Beispiel-Analyse, solange keine echte KI angebunden ist.

    Statt einer einzigen festen Antwort erkennt der Mock anhand von
    Schluesselwoertern im (anonymisierten) Prompt den Fehlertyp und liefert
    eine dazu passende Einschaetzung. So bleibt die Pipeline auch bei
    unterschiedlichen Fehlern nachvollziehbar, ohne eine externe KI zu
    kontaktieren. Es ist bewusst keine echte Sprachmodell-Analyse.
    """

    # (Schluesselwoerter, Klassifikation, Konfidenz, Ursache, Loesungshinweis)
    # - Reihenfolge = Prioritaet.
    _RULES = [
        (("connection refused", "max retries", "failed to establish",
          "could not connect", "connectionerror"),
         "Infrastrukturproblem", "hoch",
         "Der angesprochene Dienst war zum Testzeitpunkt nicht erreichbar "
         "(Verbindung abgelehnt). Das deutet auf einen nicht laufenden oder "
         "nicht erreichbaren Backend-/Netzwerkdienst hin, nicht auf einen "
         "Fehler im Test selbst.",
         "Pruefen, ob der Ziel-Dienst laeuft und erreichbar ist (Host, Port, "
         "Firewall, VPN). Fuer stabile Tests den externen Aufruf in der "
         "Testumgebung durch einen Stub/Mock ersetzen oder einen Health-Check "
         "vorschalten."),

        (("read timed out", "timed out", "timeouterror", "read timeout"),
         "Infrastrukturproblem", "mittel",
         "Der Dienst hat die Verbindung angenommen, aber nicht innerhalb des "
         "Timeouts geantwortet. Typisch bei Ueberlast, einer langsamen "
         "Abhaengigkeit oder einem zu knapp gesetzten Timeout.",
         "Antwortzeit des Dienstes pruefen und das Timeout ggf. erhoehen. Liegt "
         "es an einer langsamen Abhaengigkeit, diese in der Testumgebung mocken, "
         "damit der Test deterministisch bleibt."),

        (("401 unauthorized", "unauthorized", "token expired", "token abgelaufen"),
         "Testdatenproblem", "hoch",
         "Die Authentifizierung wurde abgelehnt (HTTP 401). Das Zugangs-Token "
         "war ungueltig oder abgelaufen ein Anmelde-/Token-Problem, kein "
         "fachlicher Fehler im getesteten Ablauf.",
         "Vor dem Test ein frisches, gueltiges Token beziehen bzw. die "
         "Test-Zugangsdaten erneuern. Tokenlaufzeit pruefen und die Anmeldung "
         "in den Setup-Schritt verlagern."),

        (("500 internal server error", "internal server error"),
         "Programmfehler", "hoch",
         "Der Server hat mit einem internen Fehler geantwortet (HTTP 500). Die "
         "Ursache liegt im Backend, nicht im Testskript.",
         "Server-Logs zum Zeitpunkt des Fehlers auswerten, den ausloesenden "
         "Request isoliert reproduzieren und den serverseitigen Stacktrace "
         "analysieren."),

        (("keyerror",),
         "Programmfehler", "mittel",
         "Es wurde auf ein Feld zugegriffen, das in der Datenstruktur fehlt "
         "(KeyError). Meist wurde der API-Vertrag geaendert (Feld umbenannt "
         "oder entfernt) oder die Antwort hat ein unerwartetes Format.",
         "Die tatsaechliche Antwortstruktur mit der erwarteten abgleichen. Auf "
         "den neuen Feldnamen umstellen oder den Zugriff absichern (z. B. "
         "dict.get mit Default) und den API-Vertrag verifizieren."),

        (("assertionerror",),
         "Testfehler", "niedrig",
         "Erwarteter und tatsaechlicher Wert stimmen nicht ueberein "
         "(fehlgeschlagene Zusicherung). Entweder hat sich die Logik geaendert "
         "oder die Test-Erwartung ist veraltet.",
         "Erwarteten und tatsaechlichen Wert aus der Meldung vergleichen, "
         "entscheiden welche Seite korrekt ist und gezielt die Implementierung "
         "ODER die Erwartung anpassen nicht beide blind angleichen."),

        (("valueerror", "ungueltig", "invalid", "rfc"),
         "Testdatenproblem", "mittel",
         "Eine Eingabe hat die Validierung nicht bestanden (ValueError). Der "
         "uebergebene Wert entspricht nicht dem erwarteten Format.",
         "Den Eingabewert gegen die Formatregel pruefen. Testdaten korrigieren "
         "oder falls der Wert gueltig sein sollte die Validierungsregel "
         "anpassen."),
    ]

    _FALLBACK = (
        "Unbekannt", "niedrig",
        "Der Test ist mit einer Ausnahme fehlgeschlagen. Aus Schritt, "
        "Fehlermeldung und Stacktrace laesst sich der genaue Ausloeser "
        "eingrenzen.",
        "Den Stacktrace von unten nach oben lesen, um die ausloesende "
        "Codezeile zu finden, und den Schritt isoliert reproduzieren.",
    )

    def _match_rule(self, text):
        """Liefert (Klassifikation, Konfidenz, Ursache, Loesungshinweis,
        Regel-Index) zum Text."""
        text = (text or "").lower()
        for index, (keywords, category, confidence, cause, hint) in enumerate(self._RULES):
            if any(keyword in text for keyword in keywords):
                return category, confidence, cause, hint, index
        return self._FALLBACK + (-1,)

    def analyze(self, prompt):
        category, confidence, cause, hint, _ = self._match_rule(prompt)
        # Der "keine echte KI"-Hinweis wandert in die Massnahme so bleibt
        # das Dict bei exakt den vier Feldern des echten Formats.
        return {
            "klassifikation": category,
            "ursache": cause,
            "massnahme": hint + "\n\n(Hinweis: regelbasierte Beispiel-Analyse "
                         "des Mock-Adapters es wurde keine echte KI "
                         "kontaktiert.)",
            "konfidenz": confidence,
        }

    def chat(self, messages):
        """Regelbasierte Beispiel-Antwort auf Rueckfragen: bezieht sich auf
        den im Verlauf enthaltenen Fehlerkontext, ohne echte KI."""
        context = " ".join(
            m.get("content", "") for m in messages if m.get("role") == "user"
        )
        _, _, cause, hint, _ = self._match_rule(context)
        last_question = ""
        for message in reversed(messages):
            if message.get("role") == "user":
                last_question = message.get("content", "")
                break
        return (
            "Zu deiner Rueckfrage \"" + last_question.strip()[:120] + "\":\n"
            "Bezogen auf diesen Fehler bleibt die Einschaetzung: " + cause + "\n"
            "Konkreter naechster Schritt: " + hint + "\n\n"
            "(Hinweis: regelbasierte Beispiel-Antwort des Mock-Adapters es "
            "wurde keine echte KI kontaktiert.)"
        )

    def cluster(self, groups):
        """Heuristisches Beispiel-Clustering: Gruppen, deren Fehlermeldung
        dieselbe Mock-Regel trifft (z. B. beide 'Verbindung abgelehnt'),
        gelten als vermutlich gleiche Ursache."""
        by_rule = {}
        for group in groups:
            text = (group.get("step") or "") + " " + (group.get("normalizedMessage") or "")
            _, _, _, _, rule_index = self._match_rule(text)
            if rule_index >= 0:
                by_rule.setdefault(rule_index, []).append(group["id"])
        clusters = []
        reasons = {
            0: "Beide Meldungen deuten auf einen nicht erreichbaren Dienst hin (Verbindung abgelehnt).",
            1: "Beide Meldungen deuten auf Zeitueberschreitungen desselben Musters hin.",
            2: "Beide Meldungen deuten auf ein Authentifizierungs-/Token-Problem hin.",
            3: "Beide Meldungen deuten auf serverseitige Fehler (HTTP 500) hin.",
            4: "Beide Meldungen deuten auf ein fehlendes Feld im API-Vertrag hin (KeyError).",
            5: "Beide Meldungen sind fehlgeschlagene Zusicherungen (AssertionError).",
            6: "Beide Meldungen sind Validierungsfehler bei Eingabewerten.",
        }
        for rule_index, ids in by_rule.items():
            if len(ids) >= 2:
                clusters.append({
                    "ids": ids,
                    "reason": reasons.get(rule_index, "Gleiches Fehlermuster erkannt.")
                              + " (Mock-Heuristik, keine echte KI.)",
                })
        return clusters


class OpenAICompatibleClient(AIClient):
    """Adapter fuer eine OpenAI-kompatible Chat-API.

    Die Basis-URL enthaelt den API-Praefix des jeweiligen Anbieters, der
    Adapter haengt nur noch ``/chat/completions`` an:

        echtes OpenAI:   https://api.openai.com/v1
        Open WebUI:      http://<host>/api      (kein /v1!)
    """

    def __init__(self, base_url, api_key, model, timeout):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def analyze(self, prompt):
        response = self.chat([
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ])
        return parse_analysis_response(response)

    def cluster(self, groups):
        response = self.chat([
            {"role": "system", "content": CLUSTER_SYSTEM_PROMPT},
            {"role": "user", "content": build_cluster_prompt(groups)},
        ])
        return parse_cluster_response(response)

    def chat(self, messages):
        url = self.base_url + "/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = "Bearer " + self.api_key
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.2,
            "stream": False,
        }

        try:
            response = requests.post(
                url, json=payload, headers=headers, timeout=self.timeout
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except requests.exceptions.Timeout as exc:
            raise AIClientError(
                "Die KI hat nicht rechtzeitig geantwortet (Timeout)."
            ) from exc
        except requests.exceptions.RequestException as exc:
            raise AIClientError(
                "Die KI-API ist nicht erreichbar: " + str(exc)
            ) from exc
        except (KeyError, ValueError, IndexError) as exc:
            raise AIClientError(
                "Die KI-Antwort hatte ein unerwartetes Format."
            ) from exc


def get_ai_client():
    """Liefert den konfigurierten KI-Adapter (Standard: Mock)."""
    if config.AI_BACKEND == "openai":
        return OpenAICompatibleClient(
            base_url=config.OPENAI_BASE_URL,
            api_key=config.OPENAI_API_KEY,
            model=config.OPENAI_MODEL,
            timeout=config.AI_TIMEOUT,
        )
    return MockAIClient()
