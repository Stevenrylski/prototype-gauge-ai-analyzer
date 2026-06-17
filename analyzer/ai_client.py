"""KI-Anbindung hinter einem austauschbaren Adapter.

Die Weboberflaeche und die Flask-Routen kennen nur die Methode
``AIClient.analyze(prompt)``. Welcher konkrete Dienst dahinter steckt
(Mock oder echte, OpenAI-kompatible API), entscheidet ``get_ai_client()``
anhand der Konfiguration. So laesst sich der KI-Dienst austauschen, ohne den
restlichen Code anzufassen.
"""

import requests

import config


class AIClientError(Exception):
    """Fehler beim KI-Aufruf (Ausfall, Timeout, ungueltige Antwort)."""


SYSTEM_PROMPT = (
    "Du bist ein Assistent, der fehlgeschlagene automatisierte Tests (Gauge) "
    "analysiert. Antworte auf Deutsch, knapp und konkret. Gliedere deine "
    "Antwort in genau zwei Abschnitte:\n"
    "Wahrscheinliche Ursache: <kurze Einschaetzung>\n"
    "Loesungshinweis: <konkreter naechster Schritt>"
)


def build_prompt(failure):
    """Baut den Nutzer-Prompt aus einem (bereits anonymisierten) Fehler-Datensatz."""
    parts = [
        "Ein automatisierter Test ist fehlgeschlagen.",
        "",
        "Schritt: " + (failure.get("step") or "(unbekannt)"),
        "Fehlermeldung: " + (failure.get("errorMessage") or "(keine)"),
    ]
    stack = failure.get("stackTrace")
    if stack:
        parts += ["", "Stacktrace:", stack]
    return "\n".join(parts)


class AIClient:
    """Schnittstelle, die jeder konkrete KI-Adapter implementiert."""

    def analyze(self, prompt):
        raise NotImplementedError


class MockAIClient(AIClient):
    """Liefert eine feste Beispielantwort, solange keine echte API verfuegbar ist."""

    def analyze(self, prompt):
        return (
            "Wahrscheinliche Ursache: Der erwartete und der tatsaechliche Wert "
            "stimmen nicht ueberein. Vermutlich wurde die Test-Erwartung oder die "
            "zugrunde liegende Logik veraendert, ohne den jeweils anderen Teil "
            "anzupassen.\n"
            "Loesungshinweis: Vergleiche erwarteten und tatsaechlichen Wert in der "
            "Fehlermeldung. Pruefe, ob die Erwartung im Test oder die Implementierung "
            "im Schritt korrigiert werden muss, und passe die richtige Seite an.\n"
            "\n"
            "(Hinweis: Beispielantwort des Mock-Adapters - es wurde keine echte KI "
            "kontaktiert.)"
        )


class OpenAICompatibleClient(AIClient):
    """Adapter fuer eine selbstgehostete, OpenAI-kompatible Chat-API."""

    def __init__(self, base_url, api_key, model, timeout):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def analyze(self, prompt):
        url = self.base_url + "/v1/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = "Bearer " + self.api_key
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
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
