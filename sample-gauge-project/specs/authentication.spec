# Anmeldung & Registrierung

Prueft die Authentifizierung von Kunden und die Gast-Registrierung gegen die
Shop-API (api.shop.example.com).

## Anmeldung mit gueltigen Zugangsdaten

tags: auth, smoke

* Der Kunde "anna.beispiel@kunden.shop-example.com" meldet sich mit gueltigem Token an
* Die Anmeldung ist erfolgreich

## Anmeldung mit abgelaufenem Token

tags: auth

* Der Kunde "anna.beispiel@kunden.shop-example.com" meldet sich mit abgelaufenem Token an
* Die Anmeldung ist erfolgreich

## Gast-Registrierung mit ungueltiger E-Mail

tags: auth, validation

* Ein Gast registriert sich mit der E-Mail "max.mustermann(at)example.de"
