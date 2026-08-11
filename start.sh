#!/usr/bin/env bash
#
# Startet den Gauge AI Analyzer auf macOS.
#
#   ./start.sh           Weboberflaeche starten (nutzt den vorhandenen Report)
#   ./start.sh --tests   vorher einen frischen Gauge-Testlauf erzeugen
#
# Legt fehlende Python-venvs beim ersten Aufruf automatisch an.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PATH="/opt/homebrew/bin:$PATH"   # damit gauge gefunden wird
# Port 5000 ist auf macOS oft von AirPlay (ControlCenter) belegt -
# dann einfach mit  PORT=5050 ./start.sh  starten.
PORT="${PORT:-5000}"

echo "==> Gauge AI Analyzer"

# --- Erst-Setup: Analyzer-venv anlegen, falls noch nicht vorhanden ---
if [ ! -d "$ROOT/analyzer/.venv" ]; then
  echo "    Lege Analyzer-venv an und installiere Abhaengigkeiten ..."
  python3 -m venv "$ROOT/analyzer/.venv"
  "$ROOT/analyzer/.venv/bin/pip" install -q --upgrade pip
  "$ROOT/analyzer/.venv/bin/pip" install -q -r "$ROOT/analyzer/requirements.txt"
fi

# --- Optional: frischer Gauge-Testlauf (erzeugt result.json neu) ---
if [ "${1:-}" = "--tests" ]; then
  if [ ! -d "$ROOT/sample-gauge-project/.venv" ]; then
    echo "    Lege Gauge-Projekt-venv an und installiere getgauge ..."
    python3 -m venv "$ROOT/sample-gauge-project/.venv"
    "$ROOT/sample-gauge-project/.venv/bin/pip" install -q --upgrade pip
    "$ROOT/sample-gauge-project/.venv/bin/pip" install -q -r "$ROOT/sample-gauge-project/requirements.txt"
  fi
  echo "    Fuehre Gauge-Testlauf aus (erzeugt frischen result.json) ..."
  ( cd "$ROOT/sample-gauge-project" && source .venv/bin/activate && gauge run specs )
  echo "    Gauge-Lauf beendet (fehlgeschlagene Tests sind hier gewollt)."
fi

# --- evtl. laufenden Analyzer stoppen (nur eigene Python-Prozesse, nicht
# --- z. B. AirPlay/ControlCenter, das auf macOS ebenfalls Port 5000 nutzt) ---
EXISTING="$(lsof -ti tcp:$PORT 2>/dev/null)"
if [ -n "$EXISTING" ]; then
  for PID in $EXISTING; do
    if ps -p "$PID" -o command= | grep -qi "python.*app.py"; then
      echo "    Stoppe alten Analyzer (PID $PID) auf Port $PORT ..."
      kill -9 "$PID" 2>/dev/null
      sleep 1
    else
      echo "!!  Port $PORT ist von einem fremden Prozess belegt:"
      ps -p "$PID" -o command=
      echo "    Bitte mit anderem Port starten, z. B.:  PORT=5050 ./start.sh"
      exit 1
    fi
  done
fi

# --- Analyzer starten ---
echo "    Starte Analyzer ..."
( cd "$ROOT/analyzer" && PORT="$PORT" nohup .venv/bin/python app.py > /tmp/gauge-analyzer.log 2>&1 & )
sleep 3

# --- Health-Check + Browser oeffnen ---
CODE="$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:$PORT/" 2>/dev/null)"
if [ "$CODE" = "200" ]; then
  echo "==> Laeuft auf http://127.0.0.1:$PORT  (oeffne im Browser)"
  open "http://127.0.0.1:$PORT"
else
  echo "!!  Server reagiert nicht (HTTP $CODE). Letzte Log-Zeilen:"
  tail -n 20 /tmp/gauge-analyzer.log
  exit 1
fi
