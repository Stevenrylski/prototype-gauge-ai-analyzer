"""Gauge-Step-Implementierungen fuer die Webshop-Testsuite.

Die Schritte rufen das simulierte Backend (shop_backend) auf. Ein Teil der
Szenarien besteht, ein Teil schlaegt mit realistischen Fehlern fehl - wie ein
echter CI-Lauf eines Online-Shops. Die Fehler (samt Stacktrace) landen im
JSON-Report und werden anschliessend vom Analyzer ausgewertet.
"""

import os
import sys

# Das step_impl-Verzeichnis in den Pfad legen, damit das Geschwister-Modul
# shop_backend unabhaengig vom Aufrufkontext importierbar ist.
sys.path.insert(0, os.path.dirname(__file__))

from getgauge.python import step, before_scenario, Messages  # noqa: E402

import shop_backend as shop  # noqa: E402

# Kleiner Produktkatalog fuer die (bestehenden) Suchtests.
CATALOG = {
    "kopfhoerer": ["BT-Over-Ear X3", "In-Ear Sport S1", "Studio Pro"],
    "usb-kabel": ["USB-C 1m", "USB-C 2m"],
    "tastatur": ["Mechanisch TKL"],
}

# Zustand innerhalb eines Szenarios (wird vor jedem Szenario zurueckgesetzt).
_state = {}


@before_scenario()
def reset_state():
    _state.clear()
    _state["session"] = None
    _state["cart_total"] = None


@before_scenario("<needs-db>")
def setup_test_database():
    """Setup-Hook: baut die Verbindung zur Test-DB auf (schlaegt hier fehl)."""
    shop.connect_test_database()


# ---------------------------------------------------------------------------
# Authentifizierung
# ---------------------------------------------------------------------------

@step("Der Kunde <email> meldet sich mit gueltigem Token an")
def login_valid(email):
    _state["session"] = shop.login(email, token="valid")


@step("Der Kunde <email> meldet sich mit abgelaufenem Token an")
def login_expired(email):
    _state["session"] = shop.login(email, token="expired")


@step("Die Anmeldung ist erfolgreich")
def login_succeeded():
    assert _state.get("session"), "Es existiert keine gueltige Session."
    Messages.write_message("Angemeldet als {0}".format(_state["session"]["customer"]))


@step("Ein Gast registriert sich mit der E-Mail <email>")
def guest_register(email):
    shop.register_guest(email)


# ---------------------------------------------------------------------------
# Katalog / Lager
# ---------------------------------------------------------------------------

@step("Die Produktsuche nach <begriff> liefert mindestens <n> Treffer")
def search_products(begriff, n):
    hits = CATALOG.get(begriff.lower().strip(), [])
    Messages.write_message("Suche '{0}' -> {1} Treffer".format(begriff, len(hits)))
    assert len(hits) >= int(n), (
        "Zu wenige Treffer fuer '{0}': erwartet mindestens {1}, gefunden {2}"
        .format(begriff, n, len(hits))
    )


@step("Die Verfuegbarkeit des Artikels <sku> wird beim Lager-Service geprueft")
def check_inventory(sku):
    result = shop.check_inventory(sku)
    Messages.write_message("Bestand {0}: {1}".format(sku, result["available"]))


# ---------------------------------------------------------------------------
# Warenkorb / Checkout
# ---------------------------------------------------------------------------

@step("Der Warenkorb enthaelt folgende Positionen <table>")
def fill_cart(table):
    items = []
    for price, qty in zip(
        table.get_column_values_with_name("Einzelpreis"),
        table.get_column_values_with_name("Menge"),
    ):
        items.append((float(price), int(qty)))
    _state["cart_total"] = shop.cart_total(items)
    Messages.write_message("Warenkorbsumme berechnet: {0} EUR".format(_state["cart_total"]))


@step("Die Warenkorbsumme betraegt <betrag> Euro")
def assert_cart_total(betrag):
    expected = float(betrag)
    actual = _state["cart_total"]
    assert actual == expected, (
        "Warenkorbsumme nach Rabatt falsch: erwartet {0:.2f} EUR, "
        "berechnet {1:.2f} EUR (Mengenrabatt von 15 % scheint nicht "
        "angewendet zu werden)".format(expected, actual)
    )


@step("Die Endsumme der Bestellung <order_id> inkl. Versand wird berechnet")
def order_total(order_id):
    total = shop.order_total_with_shipping(order_id)
    Messages.write_message("Endsumme {0}: {1} EUR".format(order_id, total))


@step("Die Bestellung <order_id> wird ueber das Bezahl-Gateway bezahlt")
def pay_order(order_id):
    shop.charge_payment(order_id, amount_eur=64.57)
    Messages.write_message("Zahlung fuer {0} erfasst".format(order_id))
