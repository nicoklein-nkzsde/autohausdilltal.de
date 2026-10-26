#!/bin/bash
# Fahrzeug-Sync von diesem Mac aus.
#
# Hintergrund: mobile.de beantwortet Anfragen aus Rechenzentren (und damit aus
# GitHub Actions) mit HTTP 403. Von einem normalen Privatanschluss aus geht der
# Abruf durch. Deshalb läuft der Sync bis zur Freischaltung der mobile.de-API
# hier lokal, angestoßen von einem LaunchAgent alle 6 Stunden.
#
# Sobald die API-Secrets im GitHub-Repo liegen, übernimmt der Actions-Workflow
# von selbst und dieser Job kann abgeschaltet werden:
#   launchctl bootout gui/$(id -u)/de.autohausdilltal.synccars
#   rm ~/Library/LaunchAgents/de.autohausdilltal.synccars.plist
#   rm -rf ~/Library/Application\ Support/autohausdilltal-sync

set -uo pipefail

# Eigener Klon ausserhalb von ~/Desktop: macOS verweigert LaunchAgents den
# Zugriff auf Desktop/Dokumente/Downloads (TCC), ein Lauf dort scheitert mit
# "Operation not permitted". Dieser Klon dient nur dem Sync – der Arbeitsklon
# auf dem Desktop bleibt unberuehrt und holt sich die Commits per git pull.
REPO="${SYNC_REPO:-$HOME/Library/Application Support/autohausdilltal-sync/repo}"
LOG="$HOME/Library/Logs/autohausdilltal-sync.log"
# Das System-Python nutzt die Schlüsselbund-Zertifikate; die python.org-
# Installation nicht, die scheitert an CERTIFICATE_VERIFY_FAILED.
PY="/usr/bin/python3"

export PATH="/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin"

log() { printf '%s  %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >> "$LOG"; }

cd "$REPO" || { log "FEHLER: Repo nicht gefunden"; exit 1; }

# Nur weitermachen, wenn das Arbeitsverzeichnis sauber ist – sonst würden
# Änderungen, an denen gerade gearbeitet wird, mit committet.
DIRTY="$(git status --porcelain -- index.html data/cars.json sitemap.xml)"
if [ -n "$DIRTY" ]; then
  log "ÜBERSPRUNGEN: ungesicherte Änderungen an index.html/cars.json/sitemap.xml"
  exit 0
fi

if ! git pull --rebase --quiet 2>>"$LOG"; then
  log "FEHLER: git pull fehlgeschlagen – Abbruch"
  exit 1
fi

OUT="$("$PY" scripts/sync_cars.py --source live 2>&1)"
log "$(echo "$OUT" | tr '\n' '; ')"

if [ -z "$(git status --porcelain -- index.html data/cars.json sitemap.xml)" ]; then
  log "keine Änderung"
  exit 0
fi

COUNT="$("$PY" -c "import json,pathlib; print(json.loads(pathlib.Path('data/cars.json').read_text())['count'])")"
git add index.html data/cars.json sitemap.xml
git commit -q -m "Fahrzeuge von mobile.de synchronisiert (${COUNT} Fahrzeuge)"

if git push --quiet 2>>"$LOG"; then
  log "gepusht – ${COUNT} Fahrzeuge live"
else
  log "FEHLER: git push fehlgeschlagen (Commit liegt lokal)"
  exit 1
fi
