"""Erzeugt die Demo-Workspace-Reports fuer die Multi-Workspace-Gesamtsicht.

Hintergrund (Thesis-Demonstration): In der Praxis gibt es viele Gauge-
Workspaces. Lokal existiert nur das eine Beispielprojekt dieses Skript
erzeugt deshalb zwei zusaetzliche, realistische Gauge-JSON-Reports:

* workspace_b.json der "99x derselbe Fehler, 1x ein anderer"-Fall:
  99 Checkout-Szenarien scheitern am selben Bezahl-Gateway-Fehler (jeweils
  mit anderer Bestellnummer und Speicheradresse erst die Normalisierung
  macht daraus EINE Gruppe), dazu genau ein fachlich anderer Fehler.
* workspace_c.json ueberlappt gezielt mit dem echten Beispielprojekt
  (gleicher shipping_cost-KeyError, gleicher Lager-Timeout, gleicher
  Gateway-Ausfall mit anderen dynamischen Werten) plus ein nur hier
  auftretender Fehler. Damit laesst sich zeigen: "Dieser Fehler tritt in
  X von Y Workspaces auf."

Aufruf (erzeugt die Dateien neben diesem Skript in workspaces/):

    python3 generate_workspaces.py
"""

import json
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent / "workspaces"

# Ein realistisch wirkender getgauge-Stacktrace. Pfad/Zeile variieren pro
# Workspace, die Speicheradressen pro Vorkommen (werden normalisiert).
STACK_TEMPLATE = (
    "Traceback (most recent call last):\n"
    '  File "/Users/ci-runner/workspaces/{project}/.venv/lib/python3.14/'
    'site-packages/getgauge/executor.py", line 35, in execute_method\n'
    "    step_impl(*params)\n"
    '  File "/Users/ci-runner/workspaces/{project}/step_impl/{module}.py", '
    "line {line}, in {function}\n"
    "    {code}\n"
    "{exception}"
)


def _failed_step(step_text, error_message, stack):
    return {
        "itemType": "step",
        "stepText": step_text,
        "result": {
            "status": "failed",
            "errorMessage": error_message,
            "stackTrace": stack,
        },
    }


def _scenario(heading, steps):
    return {"scenarioHeading": heading, "items": steps}


def _spec(heading, scenarios):
    return {"specHeading": heading, "scenarios": scenarios}


def _report(project, timestamp, specs, failed_scenarios, total_scenarios):
    passed = total_scenarios - failed_scenarios
    rate = round(passed * 100 / total_scenarios) if total_scenarios else 0
    return {
        "projectName": project,
        "timestamp": timestamp,
        "executionStatus": "failed",
        "successRate": rate,
        "failedSpecsCount": len(specs),
        "failedScenariosCount": failed_scenarios,
        "passedScenariosCount": passed,
        "specResults": specs,
    }


def _payment_error(order_id, address):
    """Der Bezahl-Gateway-Fehler des Beispielprojekts mit variierenden
    dynamischen Werten (Bestellnummer nur im Schritt, Adresse in der Meldung)."""
    message = (
        "HTTPSConnectionPool(host='payment-gw.internal.shop.example.com', "
        "port=443): Max retries exceeded with url: /v1/charges (Caused by "
        "NewConnectionError('<urllib3.connection.HTTPSConnection object at "
        + address + ">: Failed to establish a new connection: "
        "[Errno 61] Connection refused'))"
    )
    step = 'Die Bestellung "' + order_id + '" wird ueber das Bezahl-Gateway bezahlt'
    return step, message


def build_workspace_b():
    """99x derselbe Gateway-Fehler (verschiedene IDs), 1x etwas anderes."""
    scenarios = []
    for i in range(1, 100):
        order_id = "ORD-2026-" + str(1000 + i)
        address = "0x" + format(0x7f9c2a400000 + i * 0x30, "x")
        step, message = _payment_error(order_id, address)
        stack = STACK_TEMPLATE.format(
            project="demo-workspace-b", module="checkout_steps", line=88,
            function="pay_order",
            code="gateway.charge(order_id, amount)",
            exception="requests.exceptions.ConnectionError: " + message,
        )
        scenarios.append(_scenario(
            "Bestellung " + order_id + " bezahlen",
            [_failed_step(step, message, stack)],
        ))

    # Der EINE andere Fehler, der zwischen den 99 auffallen soll.
    other_step = 'Der Lagerbestand des Artikels "USB-C-Hub-7in1" betraegt "5" Stueck'
    other_message = (
        "Lagerbestand falsch: erwartet 5 Stueck, tatsaechlich 3 Stueck fuer "
        "Artikel 'USB-C-Hub-7in1' (Reservierungen aus abgebrochenen "
        "Bestellungen werden offenbar nicht freigegeben)"
    )
    other_stack = STACK_TEMPLATE.format(
        project="demo-workspace-b", module="inventory_steps", line=41,
        function="assert_stock_level",
        code="assert actual == expected, message",
        exception="AssertionError: " + other_message,
    )
    scenarios.append(_scenario(
        "Lagerbestand nach Bestellabbruch",
        [_failed_step(other_step, other_message, other_stack)],
    ))

    specs = [_spec("Checkout-Regression (Nachtlauf)", scenarios)]
    return _report("demo-workspace-b", "Jul 15, 2026 at 3:12am", specs,
                   failed_scenarios=100, total_scenarios=112)


def build_workspace_c():
    """Ueberlappt gezielt mit dem Beispielprojekt + ein eigener Fehler."""
    scenarios = []

    # 1) Gleicher shipping_cost-KeyError wie im Beispielprojekt,
    #    andere Bestellnummer.
    stack = STACK_TEMPLATE.format(
        project="demo-workspace-c", module="checkout_steps", line=63,
        function="calculate_order_total",
        code='total = subtotal + response["shipping_cost"]',
        exception="KeyError: 'shipping_cost'",
    )
    scenarios.append(_scenario("Endsumme mit Versandkosten", [_failed_step(
        'Die Endsumme der Bestellung "ORD-2026-1187" inkl. Versand wird berechnet',
        "'shipping_cost'",
        stack,
    )]))

    # 2) Gleicher Lager-Timeout wie im Beispielprojekt, anderes Timeout.
    timeout_message = (
        "HTTPSConnectionPool(host='inventory.shop.example.com', port=443): "
        "Read timed out. (read timeout=10)"
    )
    stack = STACK_TEMPLATE.format(
        project="demo-workspace-c", module="inventory_steps", line=27,
        function="check_availability",
        code="response = session.get(url, timeout=10)",
        exception="requests.exceptions.ReadTimeout: " + timeout_message,
    )
    scenarios.append(_scenario("Verfuegbarkeit im Lager-Service", [_failed_step(
        'Die Verfuegbarkeit des Artikels "BT-Over-Ear-X3" wird beim Lager-Service geprueft',
        timeout_message,
        stack,
    )]))

    # 3) Gleicher Bezahl-Gateway-Ausfall wie in Workspace B / Beispielprojekt.
    for i, order_id in enumerate(("ORD-2026-2044", "ORD-2026-2045")):
        address = "0x" + format(0x7fb51e800000 + i * 0x40, "x")
        step, message = _payment_error(order_id, address)
        stack = STACK_TEMPLATE.format(
            project="demo-workspace-c", module="checkout_steps", line=88,
            function="pay_order",
            code="gateway.charge(order_id, amount)",
            exception="requests.exceptions.ConnectionError: " + message,
        )
        scenarios.append(_scenario("Bestellung " + order_id + " bezahlen",
                                   [_failed_step(step, message, stack)]))

    # 4) Ein Fehler, der NUR in diesem Workspace auftritt.
    coupon_message = (
        "500 Internal Server Error for url: "
        "https://api.shop.example.com/v1/coupons/redeem "
        "(request id 8f41c6d2-6a1b-4a7e-9d35-2f8a1b0c9e77)"
    )
    stack = STACK_TEMPLATE.format(
        project="demo-workspace-c", module="coupon_steps", line=19,
        function="redeem_coupon",
        code="response.raise_for_status()",
        exception="requests.exceptions.HTTPError: " + coupon_message,
    )
    scenarios.append(_scenario("Gutschein einloesen", [_failed_step(
        'Der Gutschein "SOMMER25" wird auf die Bestellung angewendet',
        coupon_message,
        stack,
    )]))

    specs = [_spec("Checkout und Aktionen (Nachtlauf)", scenarios)]
    return _report("demo-workspace-c", "Jul 15, 2026 at 2:47am", specs,
                   failed_scenarios=5, total_scenarios=38)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, report in (
        ("workspace_b.json", build_workspace_b()),
        ("workspace_c.json", build_workspace_c()),
    ):
        path = OUT_DIR / name
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                        encoding="utf-8")
        print("geschrieben:", path)


if __name__ == "__main__":
    main()
