"""Simuliertes Webshop-Backend ("System Under Test").

Dies ist KEIN echtes Netzwerk und kein echter Online-Shop. Es ist ein bewusst
vereinfachtes Backend, das sich nach aussen wie ein echter REST-API-Client
verhaelt und an realistischen Stellen mit echten Python-Exceptions und
mehrstufigen Stacktraces fehlschlaegt. Dadurch erzeugt ein Gauge-Lauf
realitaetsnahe Fehler-Logs, die der Analyzer auswerten kann.

Die Fehler sind absichtlich eingebaut, wie sie in der Test-Suite eines echten
Shops auftreten wuerden:
    * fehlerhafte Rabattlogik            -> AssertionError (fachlicher Fehler)
    * Bezahl-Gateway nicht erreichbar    -> ConnectionError
    * Lager-Service antwortet zu langsam -> TimeoutError
    * fehlendes Feld in der API-Antwort  -> KeyError (API-Vertrag verletzt)
    * abgelaufenes Auth-Token            -> ApiError 401
    * ungueltige Eingabe (E-Mail)        -> ValueError

Die Meldungen enthalten bewusst Hostnames, URLs, IP-Adressen und E-Mails,
damit die DSGVO-Anonymisierung des Analyzers sichtbar greift.
"""

# Adressen des simulierten Backends (tauchen in den Fehler-Logs auf).
API_BASE = "https://api.shop.example.com"
PAYMENT_HOST = "payment-gw.internal.shop.example.com"
INVENTORY_HOST = "inventory.shop.example.com"
DB_HOST = "10.42.3.18"  # Test-Datenbank (interne IP)


class ApiError(Exception):
    """HTTP-Fehlerantwort der Shop-API (vergleichbar mit requests.HTTPError)."""

    _REASON = {
        400: "Bad Request", 401: "Unauthorized", 403: "Forbidden",
        404: "Not Found", 409: "Conflict", 422: "Unprocessable Entity",
        500: "Internal Server Error", 503: "Service Unavailable",
    }

    def __init__(self, status, url, detail=""):
        self.status = status
        self.url = url
        reason = self._REASON.get(status, "HTTP Error")
        message = "{0} {1} for url: {2}".format(status, reason, url)
        if detail:
            message += " | " + detail
        super().__init__(message)


# ---------------------------------------------------------------------------
# Simulierte Transport-Schicht. Die mehrstufigen Aufrufe (Methode -> _request
# -> _open_connection) sorgen fuer realitaetsnahe, tiefe Stacktraces.
# ---------------------------------------------------------------------------

def _open_connection(host, port, timeout):
    """Simuliert den TCP-Verbindungsaufbau zu einem Host."""
    if host == PAYMENT_HOST:
        # Dienst ist nicht erreichbar (z. B. Gateway down / Firewall).
        raise ConnectionError(
            "HTTPSConnectionPool(host='{0}', port={1}): "
            "Max retries exceeded with url: /v1/charges "
            "(Caused by NewConnectionError("
            "'<urllib3.connection.HTTPSConnection object at 0x10f3a2b90>: "
            "Failed to establish a new connection: "
            "[Errno 61] Connection refused'))".format(host, port)
        )
    return {"host": host, "port": port, "timeout": timeout}


def _read_response(connection, route):
    """Simuliert das Lesen der HTTP-Antwort ueber eine offene Verbindung."""
    if connection["host"] == INVENTORY_HOST:
        # Dienst nimmt die Verbindung an, antwortet aber nicht rechtzeitig.
        raise TimeoutError(
            "HTTPSConnectionPool(host='{0}', port={1}): "
            "Read timed out. (read timeout={2})".format(
                connection["host"], connection["port"], connection["timeout"]
            )
        )
    return {"status": 200, "route": route}


def _request(method, url, payload=None, timeout=30):
    """Fuehrt einen simulierten HTTP-Request aus (Verbindung + Antwort lesen)."""
    host = url.split("://", 1)[-1].split("/", 1)[0]
    route = "/" + url.split("://", 1)[-1].split("/", 1)[-1] if "/" in url.split("://", 1)[-1] else "/"
    connection = _open_connection(host, 443, timeout)
    return _read_response(connection, route)


# ---------------------------------------------------------------------------
# Fachliche API-Aufrufe des Shops.
# ---------------------------------------------------------------------------

def login(email, token):
    """Meldet einen Kunden an. Wirft ApiError(401) bei abgelaufenem Token."""
    url = API_BASE + "/v1/auth/login"
    if token == "expired":
        raise ApiError(
            401, url,
            "token expired at 2026-06-17T14:05:11Z for principal "
            "customer:" + email,
        )
    return {"customer": email, "session": "sess_8f21c4"}


def charge_payment(order_id, amount_eur):
    """Belastet die Zahlungsmethode ueber das Bezahl-Gateway."""
    url = "https://{0}/v1/charges".format(PAYMENT_HOST)
    _request("POST", url, payload={"order": order_id, "amount": amount_eur})
    return {"order": order_id, "captured": amount_eur}


def check_inventory(sku):
    """Fragt die Verfuegbarkeit eines Artikels beim Lager-Service ab."""
    url = "https://{0}/v1/stock/{1}".format(INVENTORY_HOST, sku)
    _request("GET", url, timeout=5)
    return {"sku": sku, "available": 12}


def _fetch_order(order_id):
    """Liefert die (simulierte) API-Antwort zu einer Bestellung.

    Hinweis: Das Feld 'shipping_cost' fehlt absichtlich - so, wie es bei einer
    geaenderten API-Version (Vertragsbruch) vorkommen wuerde.
    """
    return {
        "order_id": order_id,
        "currency": "EUR",
        "items": 3,
        "subtotal": 89.97,
        # "shipping_cost": 4.99,   <- in dieser API-Version entfernt
        "status": "confirmed",
    }


def order_total_with_shipping(order_id):
    """Berechnet die Endsumme inkl. Versand. Greift auf 'shipping_cost' zu."""
    order = _fetch_order(order_id)
    return order["subtotal"] + order["shipping_cost"]


def cart_total(items):
    """Summiert die Warenkorb-Positionen und zieht den Mengenrabatt ab.

    Enthaelt einen absichtlichen Regressionsfehler: ab 3 Artikeln sollen
    15 % Rabatt gewaehrt werden, tatsaechlich werden faelschlich nur 10 %
    abgezogen.
    """
    subtotal = sum(price * qty for price, qty in items)
    quantity = sum(qty for _, qty in items)
    if quantity >= 3:
        # BUG: muesste 0.15 sein, ist aber 0.10 -> falsche Endsumme.
        return round(subtotal * (1 - 0.10), 2)
    return round(subtotal, 2)


def register_guest(email):
    """Validiert die E-Mail eines Gast-Kontos (vereinfachte RFC-5322-Pruefung)."""
    if "@" not in email or email.startswith("@") or email.endswith("@") or " " in email:
        raise ValueError(
            "Ungueltige E-Mail-Adresse: '{0}' entspricht nicht RFC 5322 "
            "(erwartet local-part@domain)".format(email)
        )
    return {"guest": email}


def connect_test_database():
    """Baut die Verbindung zur Test-Datenbank auf (Einsatz im Setup-Hook)."""
    raise ConnectionError(
        "could not connect to server: Connection refused\n"
        "\tIs the server running on host \"{0}\" and accepting TCP/IP "
        "connections on port 5432?".format(DB_HOST)
    )
