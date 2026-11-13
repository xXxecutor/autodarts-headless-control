#!/usr/bin/env bash
# Autodarts Headless Control – automatisches Update
#
# Prüft, ob auf GitHub eine neuere Version veröffentlicht wurde, und installiert
# sie mit dem Installer genau dieser Version. Läuft täglich über
# autodarts-headless-control-update.timer. Abschalten: in der Admin-Seite
# (System > Automatische Updates; der Timer startet dann gar nicht erst) oder
# fest mit HEADLESS_AUTO_UPDATE=0 in /etc/autodarts-headless-control.env.
#
#   self-update.sh           prüfen und ggf. aktualisieren
#   self-update.sh --check   nur prüfen (Rückgabe 0 = aktuell, 10 = Update verfügbar)

set -Eeuo pipefail

REPO="xXxecutor/autodarts-headless-control"
INSTALL_DIR="/opt/autodarts-headless-control"
ENV_FILE="/etc/autodarts-headless-control.env"

log() { echo "[autodarts-headless-control-update] $*"; }

if [[ "${1:-}" != "--check" ]] && \
    grep -Eq '^[[:space:]]*HEADLESS_AUTO_UPDATE[[:space:]]*=[[:space:]]*"?0"?[[:space:]]*$' "${ENV_FILE}" 2>/dev/null; then
    log "Automatische Updates sind deaktiviert (HEADLESS_AUTO_UPDATE=0)."
    exit 0
fi

installed="$(sed -n 's/^version[[:space:]]*=[[:space:]]*"\(.*\)"/\1/p' "${INSTALL_DIR}/pyproject.toml" 2>/dev/null | head -n1)"

# Die URL von ".../releases/latest" leitet auf ".../releases/tag/v<Version>" weiter.
latest_url="$(curl -fsSL -o /dev/null -w '%{url_effective}' "https://github.com/${REPO}/releases/latest" 2>/dev/null || true)"
latest="${latest_url##*/tag/}"
latest="${latest#v}"

if [[ -z "${latest}" || "${latest}" == "${latest_url}" ]]; then
    log "Keine veröffentlichte Version gefunden (offline oder noch kein Release)."
    exit 0
fi

newest="$(printf '%s\n%s\n' "${installed:-0}" "${latest}" | sort -V | tail -n1)"
if [[ "${latest}" == "${installed}" || "${newest}" != "${latest}" ]]; then
    log "Aktuell: Version ${installed:-unbekannt}."
    exit 0
fi

log "Neue Version ${latest} verfügbar (installiert: ${installed:-unbekannt})."
[[ "${1:-}" == "--check" ]] && exit 10

tmp="$(mktemp -d)"
trap 'rm -rf "${tmp}"' EXIT
curl -fsSL --retry 3 -o "${tmp}/install.sh" \
    "https://github.com/${REPO}/releases/download/v${latest}/install.sh"
bash "${tmp}/install.sh" --version "${latest}"
log "Update auf Version ${latest} abgeschlossen."
