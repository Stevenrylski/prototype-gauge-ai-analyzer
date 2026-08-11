# Warenkorb & Bezahlung

Prueft die Warenkorb-Berechnung sowie den Checkout ueber das Bezahl-Gateway
(payment-gw.internal.shop.example.com).

## Warenkorbsumme mit Mengenrabatt

tags: cart

* Der Warenkorb enthaelt folgende Positionen

     |Artikel        |Einzelpreis|Menge|
     |---------------|-----------|-----|
     |BT-Over-Ear X3 |49.99      |1    |
     |USB-C Kabel 2m |12.99      |2    |

* Die Warenkorbsumme betraegt "64.57" Euro

## Endsumme inklusive Versand

tags: checkout

* Die Endsumme der Bestellung "ORD-2026-0098" inkl. Versand wird berechnet

## Kreditkartenzahlung wird erfasst

tags: checkout, payment

* Die Bestellung "ORD-2026-0098" wird ueber das Bezahl-Gateway bezahlt

## Bezahlung im Express-Checkout

tags: checkout, payment

* Die Bestellung "ORD-2026-0098" wird ueber das Bezahl-Gateway bezahlt
