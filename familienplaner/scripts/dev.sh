#!/usr/bin/env bash
# Familienplaner lokal einrichten und starten – Linux, WSL (Windows) oder Raspberry Pi.
#
#   scripts/dev.sh              einrichten (falls nötig), Frontend bauen, starten
#   scripts/dev.sh --demo       zusätzlich Beispieldaten anlegen (Familie, Termine, Veranstaltungen)
#   scripts/dev.sh --test       nur die automatischen Tests ausführen
#   scripts/dev.sh --reset      lokale Daten löschen (backend/data) und neu beginnen
#   scripts/dev.sh --dev        Entwicklungsmodus: Backend mit Auto-Reload + Vite-Dev-Server
#
#   PORT=8080 scripts/dev.sh    anderer Port (Standard 8000)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
PORT="${PORT:-8000}"
DEMO=0 TEST=0 RESET=0 DEV=0

bold() { printf '\033[1m%s\033[0m\n' "$*"; }
info() { printf '  → %s\n' "$*"; }
fail() { printf '\n\033[31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

for arg in "$@"; do
  case "$arg" in
    --demo) DEMO=1 ;;
    --test) TEST=1 ;;
    --reset) RESET=1 ;;
    --dev) DEV=1 ;;
    -h|--help) sed -n '2,11p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) fail "Unbekannte Option: $arg (Hilfe: scripts/dev.sh --help)" ;;
  esac
done

# --- Umgebung prüfen ------------------------------------------------------------------------
bold "Familienplaner – lokaler Start"

if grep -qi microsoft /proc/version 2>/dev/null; then
  info "WSL erkannt"
  case "$ROOT" in
    /mnt/*) printf '  ⚠ Das Projekt liegt auf einem Windows-Laufwerk (%s).\n    npm und Python sind dort sehr langsam. Besser im Linux-Dateisystem klonen, z. B. ~/familienplaner.\n' "$ROOT" ;;
  esac
fi

PY=""
for candidate in python3.13 python3.12 python3.11 python3; do
  if command -v "$candidate" >/dev/null 2>&1 &&
     "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
    PY="$candidate"; break
  fi
done
[ -n "$PY" ] || fail "Python 3.11 oder neuer fehlt.
    Ubuntu 24.04:  sudo apt install python3 python3-venv
    Ubuntu 22.04:  sudo apt install python3.11 python3.11-venv"
info "Python: $($PY -V)"

command -v node >/dev/null 2>&1 || fail "Node.js fehlt (Version 20 oder neuer). Installation z. B. mit nvm:
    curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
    (Terminal neu öffnen)  nvm install 22"
NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]')"
[ "$NODE_MAJOR" -ge 18 ] || fail "Node.js $(node -v) ist zu alt (mindestens 18, empfohlen 22): nvm install 22"
info "Node.js: $(node -v)"

# --- Backend --------------------------------------------------------------------------------
VENV="$BACKEND/.venv"
if [ ! -x "$VENV/bin/python" ]; then
  info "Python-Umgebung anlegen …"
  "$PY" -m venv "$VENV" 2>/dev/null || fail "venv konnte nicht angelegt werden. Fehlt das Paket python3-venv?
    sudo apt install $("$PY" -c 'import sys; print(f"python3.{sys.version_info.minor}")')-venv"
fi
STAMP="$VENV/.installed"
if [ ! -f "$STAMP" ] || [ "$BACKEND/pyproject.toml" -nt "$STAMP" ]; then
  info "Python-Pakete installieren (einmalig, ca. 1 min) …"
  "$VENV/bin/pip" install -q --upgrade pip
  "$VENV/bin/pip" install -q -e "$BACKEND[dev]"
  touch "$STAMP"
fi

# --- Frontend -------------------------------------------------------------------------------
if [ ! -d "$FRONTEND/node_modules" ] || [ "$FRONTEND/package-lock.json" -nt "$FRONTEND/node_modules" ]; then
  info "Node-Pakete installieren …"
  (cd "$FRONTEND" && npm ci --no-audit --no-fund --loglevel=error)
  touch "$FRONTEND/node_modules"
fi

# --- Tests ----------------------------------------------------------------------------------
if [ "$TEST" = 1 ]; then
  bold "Backend-Tests"
  (cd "$BACKEND" && FP_CONFIG_FILE=/nonexistent "$VENV/bin/python" -m pytest -q)
  bold "Frontend-Prüfung und -Tests"
  (cd "$FRONTEND" && npm run --silent check && TZ=Europe/Berlin npm test --silent)
  bold "✓ Alle Tests bestanden"
  exit 0
fi

# --- Daten ----------------------------------------------------------------------------------
cd "$BACKEND"
export FP_SERVER__PORT="$PORT"
# Ohne eigene config.yaml: Daten unter backend/data (nicht /etc, /var/lib)
if [ -z "${FP_CONFIG_FILE:-}" ] && [ ! -f /etc/familienplaner/config.yaml ]; then
  export FP_CONFIG_FILE="$ROOT/config/local.yaml"
  [ -f "$FP_CONFIG_FILE" ] || export FP_CONFIG_FILE=/nonexistent
fi
if [ "$RESET" = 1 ]; then
  info "Lokale Daten löschen (backend/data) …"
  rm -rf "$BACKEND/data"
fi
if [ "$DEMO" = 1 ]; then
  info "Beispieldaten anlegen …"
  "$VENV/bin/python" -m app.tools.demo
fi

# --- Start ----------------------------------------------------------------------------------
print_urls() {
  echo
  bold "Familienplaner läuft – im Windows-/Linux-Browser öffnen:"
  echo "    http://localhost:$1              normale Ansicht"
  echo "    http://localhost:$1/?kiosk=1     wie am Pi (Bildschirmtastatur, Rückkehr zu „Heute“)"
  echo "    http://localhost:$PORT/docs          API-Dokumentation"
  echo "  Beenden mit Strg+C"
  echo
}

if [ "$DEV" = 1 ]; then
  trap 'kill 0' EXIT
  "$VENV/bin/uvicorn" --factory app.main:app_factory --reload --host 0.0.0.0 --port "$PORT" &
  print_urls 5173
  (cd "$FRONTEND" && API="http://localhost:$PORT" npx vite --host 0.0.0.0 --port 5173)
else
  info "Frontend bauen …"
  (cd "$FRONTEND" && npm run --silent build >/dev/null)
  print_urls "$PORT"
  exec "$VENV/bin/uvicorn" --factory app.main:app_factory --host 0.0.0.0 --port "$PORT"
fi
