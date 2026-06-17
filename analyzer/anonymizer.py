"""DSGVO-Anonymisierung.

Bevor Fehlertexte an eine (potenziell externe) KI gehen, werden hier
personen- und infrastrukturbezogene Daten ersetzt:

* absolute Datei-Pfade (Windows und Unix) inkl. Benutzername im Pfad
* Benutzernamen (auch ausserhalb von Pfaden, sobald sie einmal erkannt wurden)
* Hostnames / FQDNs und URLs
* E-Mail-Adressen
* IP-Adressen

Das Ziel ist nicht perfekte Unkenntlichmachung, sondern ein nachvollziehbarer,
einfach erweiterbarer Filter fuer den Prototyp. Der Dateiname am Ende eines
Pfades bleibt erhalten, weil er fuer die Fehleranalyse nuetzlich und nicht
sensibel ist.
"""

import getpass
import os
import re

USER_PLACEHOLDER = "<BENUTZER>"
PATH_PLACEHOLDER = "<PFAD>"
HOST_PLACEHOLDER = "<HOST>"
EMAIL_PLACEHOLDER = "<EMAIL>"
IP_PLACEHOLDER = "<IP>"

# Benutzername aus einem Windows- oder Unix-Heimatpfad herausfischen.
_USER_IN_PATH = re.compile(r"(?:Users|home)[\\/]+([^\\/\s\"']+)", re.IGNORECASE)

# Windows-Pfad, z. B. C:\Users\srylski\projekt\datei.py
_WINDOWS_PATH = re.compile(r"[A-Za-z]:\\(?:[^\\\s\"']+\\)*([^\\\s\"']+)")

# Unix-Pfad, z. B. /home/srylski/projekt/datei.py (mind. zwei Segmente).
_UNIX_PATH = re.compile(r"/(?:[^/\s\"']+/)+([^/\s\"']+)")

_URL = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
_EMAIL = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
_IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")

# FQDN/Hostname: punktierter Name, der auf eine bekannte TLD oder eine typische
# interne Endung endet (z. B. ci-runner-07.internal.example.com). Die TLD-Liste
# verhindert, dass punktierte Code-Bezeichner wie "sock.connect" oder
# "requests.exceptions" faelschlich als Hostname gewertet werden.
_TLD = (
    "com|net|org|edu|gov|mil|int|io|dev|app|co|eu|uk|us|de|info|biz"
    "|local|internal|intranet|intern|lan|corp|home|test"
)
_FQDN = re.compile(
    r"\b(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+(?:" + _TLD + r")\b",
    re.IGNORECASE,
)


def _os_usernames():
    """Benutzernamen des aktuellen Systems, die immer entfernt werden."""
    names = set()
    for value in (os.environ.get("USERNAME"), os.environ.get("USER")):
        if value:
            names.add(value)
    try:
        names.add(getpass.getuser())
    except Exception:
        pass
    return names


# Wird beim Import einmal bestimmt.
_ALWAYS_SCRUB = _os_usernames()


def _collect_usernames(text):
    """Sammelt Benutzernamen, die in Heimatpfaden auftauchen."""
    return {match.group(1) for match in _USER_IN_PATH.finditer(text)}


def anonymize(text):
    """Gibt eine anonymisierte Kopie von ``text`` zurueck."""
    if not text:
        return text

    # In Heimatpfaden gefundene Benutzernamen plus die des aktuellen Systems.
    usernames = _collect_usernames(text) | _ALWAYS_SCRUB

    # Reihenfolge ist wichtig: zuerst spezifische Muster (URL, E-Mail, IP),
    # dann Pfade, zuletzt allgemeine Hostnames.
    text = _EMAIL.sub(EMAIL_PLACEHOLDER, text)
    text = _URL.sub(HOST_PLACEHOLDER, text)
    text = _IPV4.sub(IP_PLACEHOLDER, text)

    # Pfade auf <PFAD>/<dateiname> reduzieren (Dateiname bleibt erhalten).
    text = _WINDOWS_PATH.sub(lambda m: PATH_PLACEHOLDER + "/" + m.group(1), text)
    text = _UNIX_PATH.sub(lambda m: PATH_PLACEHOLDER + "/" + m.group(1), text)

    text = _FQDN.sub(HOST_PLACEHOLDER, text)

    # Erkannte Benutzernamen ueberall ersetzen (auch ausserhalb von Pfaden).
    for name in usernames:
        if name:
            text = re.sub(r"\b" + re.escape(name) + r"\b", USER_PLACEHOLDER, text)

    return text
