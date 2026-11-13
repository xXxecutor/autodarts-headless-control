#!/usr/bin/env bash
set -Eeuo pipefail

# Autodarts Headless Control - Debian (.deb) Package Builder
#
# Baut ein architekturunabhängiges .deb-Paket aus dem Projektordner.
# Die Dateiliste steht in installer/stage.sh, die Systemeinrichtung in
# installer/setup.sh – beides teilt sich das Paket mit install.sh.
#
# Aufruf:  ./installer/build-deb.sh [VERSION]
#          (ohne VERSION wird die Version aus pyproject.toml verwendet)
# Ergebnis: dist/autodarts-headless-control_<VERSION>_all.deb

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=installer/stage.sh
. "${PROJECT_DIR}/installer/stage.sh"

VERSION="${1:-}"
if [[ -z "${VERSION}" ]]; then
    VERSION="$(sed -n 's/^version[[:space:]]*=[[:space:]]*"\(.*\)"/\1/p' "${PROJECT_DIR}/pyproject.toml" | head -n1)"
fi
VERSION="${VERSION#v}"
[[ -n "${VERSION}" ]] || { echo "[ERROR] Keine Version gefunden." >&2; exit 1; }

DEB_NAME="${PKG_NAME}_${VERSION}_all.deb"
DIST_DIR="${DIST_DIR:-${PROJECT_DIR}/dist}"
BUILD_DIR="$(mktemp -d)"
trap 'rm -rf "${BUILD_DIR}"' EXIT

command -v dpkg-deb >/dev/null 2>&1 || { echo "[ERROR] dpkg-deb fehlt (nur auf Debian/Ubuntu verfügbar)." >&2; exit 1; }

printf '[INFO] Baue %s (Version %s)...\n' "${DEB_NAME}" "${VERSION}"

ROOT="${BUILD_DIR}/root"
mkdir -p "${ROOT}/DEBIAN"
stage_files "${PROJECT_DIR}" "${ROOT}" "lib/systemd/system" "${VERSION}"

# Paket-Metadaten
sed "s/^Version: .*/Version: ${VERSION}/" "${PROJECT_DIR}/debian/control" > "${ROOT}/DEBIAN/control"
for script in postinst prerm postrm; do
    sed 's/\r$//' "${PROJECT_DIR}/debian/${script}" > "${ROOT}/DEBIAN/${script}"
    chmod 0755 "${ROOT}/DEBIAN/${script}"
done
# Alle Dateien unter /etc sind Konfiguration: bei Updates bleiben lokale Änderungen erhalten.
(cd "${ROOT}" && find etc -type f | sed 's|^|/|' | sort) > "${ROOT}/DEBIAN/conffiles"

find "${ROOT}" -type d -exec chmod 0755 {} +

mkdir -p "${DIST_DIR}"
dpkg-deb --build --root-owner-group "${ROOT}" "${DIST_DIR}/${DEB_NAME}" >/dev/null

printf '[OK] Paket gebaut: %s/%s (%s)\n' "${DIST_DIR}" "${DEB_NAME}" "$(du -h "${DIST_DIR}/${DEB_NAME}" | cut -f1)"
