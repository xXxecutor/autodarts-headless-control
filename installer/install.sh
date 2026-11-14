#!/usr/bin/env bash
# Autodarts Headless Control – Installer
#
# Empfohlen (lädt die neueste Version von GitHub):
#   curl -fsSL https://github.com/xXxecutor/autodarts-headless-control/releases/latest/download/install.sh | sudo bash
# Ohne curl:
#   wget -qO- https://github.com/xXxecutor/autodarts-headless-control/releases/latest/download/install.sh | sudo bash
# Ohne sudo (als root):
#   su -c "wget -qO- https://github.com/xXxecutor/autodarts-headless-control/releases/latest/download/install.sh | bash"
#
# Aus einem heruntergeladenen Projektordner (Git-Checkout oder ZIP):
#   sudo ./installer/install.sh
#
# Optionen:
#   --release           neueste Version aus GitHub laden, auch wenn ein Projektordner vorhanden ist
#   --version X.Y.Z     bestimmte Release-Version installieren (impliziert --release)
#   --beta              Autodarts-Beta statt der stabilen Version installieren
#   --skip-autodarts    Autodarts selbst nicht installieren (nur Headless Control)
#   --uninstall         Headless Control entfernen (Autodarts und Kalibrierung bleiben erhalten)
#
# Debian, Ubuntu, Raspberry Pi OS, Mint & Co. erhalten das .deb-Paket (apt).
# Fedora, RHEL-Klone, Arch, Manjaro, openSUSE & Co. erhalten dieselben Dateien
# direkt; Abhängigkeiten kommen jeweils aus der Paketverwaltung der Distribution.

set -Eeuo pipefail

REPO="xXxecutor/autodarts-headless-control"
PKG_NAME="autodarts-headless-control"
MANIFEST="/var/lib/${PKG_NAME}-install/manifest"
UNIT_DIR="usr/local/lib/systemd/system"

log()  { printf '\033[1;34m[INFO]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[WARN]\033[0m %s\n' "$*" >&2; }
fail() { printf '\033[1;31m[FEHLER]\033[0m %s\n' "$*" >&2; exit 1; }

MODE="auto"
VERSION=""
ACTION="install"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --release)        MODE="release" ;;
        --version)        VERSION="${2:-}"; MODE="release"; shift ;;
        --beta)           export AUTODARTS_VERSION="beta" ;;
        --skip-autodarts) export AUTODARTS_HEADLESS_SKIP_AUTODARTS=1 ;;
        --uninstall)      ACTION="uninstall" ;;
        -h|--help)        sed -n '2,24p' "$0" 2>/dev/null || true; exit 0 ;;
        *) fail "Unbekannte Option: $1" ;;
    esac
    shift
done

# --- Voraussetzungen --------------------------------------------------------

[[ "${EUID:-$(id -u)}" -eq 0 ]] || fail "Bitte mit sudo ausführen (ohne sudo: als root per 'su -')."
[[ -f /etc/os-release ]] || fail "Betriebssystem nicht erkennbar (/etc/os-release fehlt)."
# Nur in einer Subshell einlesen: os-release definiert u. a. VERSION und würde
# sonst die gewünschte Release-Version (--version) überschreiben.
# shellcheck disable=SC1091
OS_NAME="$(. /etc/os-release && echo "${PRETTY_NAME:-${ID:-Linux}}")"
command -v systemctl >/dev/null 2>&1 || fail "systemd wird benötigt."

if command -v apt-get >/dev/null 2>&1 && command -v dpkg >/dev/null 2>&1; then
    PM="apt"
elif command -v dnf >/dev/null 2>&1; then
    PM="dnf"
elif command -v pacman >/dev/null 2>&1; then
    PM="pacman"
elif command -v zypper >/dev/null 2>&1; then
    PM="zypper"
else
    fail "Keine unterstützte Paketverwaltung gefunden (apt, dnf, pacman, zypper)."
fi
log "System: ${OS_NAME} (Paketverwaltung: ${PM})"

# --- Gemeinsame Hilfen ------------------------------------------------------

# Frisch installierte Systeme führen beim ersten Start oft automatische Updates
# aus und halten die Paketverwaltung gesperrt: warten statt abbrechen.
APT_OPTS=(-o DPkg::Lock::Timeout=900)
export ZYPP_LOCK_TIMEOUT=900
# Ubuntu: needrestart soll nicht interaktiv nachfragen.
export NEEDRESTART_MODE=a NEEDRESTART_SUSPEND=1
export DEBIAN_FRONTEND=noninteractive

WORK_DIR="$(mktemp -d)"
trap 'rm -rf "${WORK_DIR}"' EXIT
chmod 755 "${WORK_DIR}"  # apt liest lokale Pakete als Benutzer _apt

ensure_curl() {
    command -v curl >/dev/null 2>&1 && return 0
    case "${PM}" in
        apt)    apt-get "${APT_OPTS[@]}" update -qq && apt-get "${APT_OPTS[@]}" install -y -qq curl ca-certificates ;;
        dnf)    dnf install -y -q curl-minimal ca-certificates || dnf install -y -q curl ca-certificates ;;
        pacman) pacman -Sy --needed --noconfirm curl ca-certificates ;;
        zypper) zypper --non-interactive install curl ca-certificates ;;
    esac
}

download() {
    ensure_curl
    log "Lade $1"
    curl -fL --retry 3 -o "$2" "$1" || fail "Download fehlgeschlagen. Besteht eine Internetverbindung?"
}

release_url() {
    # $1: Dateiname-Muster mit VERSION-Platzhalter
    if [[ -n "${VERSION}" ]]; then
        echo "https://github.com/${REPO}/releases/download/v${VERSION#v}/${1//@V@/${VERSION#v}}"
    else
        echo "https://github.com/${REPO}/releases/latest/download/${1//@V@/latest}"
    fi
}

SCRIPT_DIR=""
if [[ -n "${BASH_SOURCE[0]:-}" && -f "${BASH_SOURCE[0]}" ]]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi
PROJECT_DIR=""
if [[ "${MODE}" == "auto" && -n "${SCRIPT_DIR}" && -f "${SCRIPT_DIR}/../app/main.py" && -f "${SCRIPT_DIR}/stage.sh" ]]; then
    PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
fi

check_network_management() {
    # Die Einrichtung übergibt WLAN-Konfigurationen automatisch an NetworkManager
    # (installer/migrate-network.py). Hier wird nur noch gewarnt, was offen bleibt.
    local iface
    if ! systemctl is-enabled --quiet NetworkManager 2>/dev/null; then
        warn "NetworkManager ist nicht aktiv. Ohne ihn funktionieren WLAN-Einrichtung und"
        warn "Setup-Hotspot nicht (LAN und alle übrigen Funktionen schon). Aktivieren mit:"
        warn "  sudo systemctl disable --now systemd-networkd iwd wicked 2>/dev/null; sudo systemctl enable --now NetworkManager"
    fi
    if [[ -f /etc/network/interfaces ]]; then
        for iface in /sys/class/net/*; do
            iface="${iface##*/}"
            [[ -d "/sys/class/net/${iface}/wireless" ]] || continue
            if grep -Eqs "^[[:space:]]*iface[[:space:]]+${iface}[[:space:]]+inet[[:space:]]+static" /etc/network/interfaces /etc/network/interfaces.d/*; then
                warn "WLAN ${iface} hat in /etc/network/interfaces eine feste IP-Adresse und wurde"
                warn "deshalb nicht automatisch an NetworkManager übergeben."
            fi
        done
    fi
}

# --- Debian-Familie: .deb-Paket ---------------------------------------------

install_deb() {
    local deb
    if [[ -n "${PROJECT_DIR}" ]]; then
        log "Projektordner gefunden: baue Paket aus ${PROJECT_DIR}"
        DIST_DIR="${WORK_DIR}" bash "${PROJECT_DIR}/installer/build-deb.sh"
        deb="$(ls "${WORK_DIR}"/${PKG_NAME}_*_all.deb | head -n1)"
    else
        deb="${WORK_DIR}/${PKG_NAME}.deb"
        download "$(release_url "${PKG_NAME}_@V@_all.deb")" "${deb}"
    fi
    chmod 644 "${deb}"

    log "Installiere Paket und Abhängigkeiten (das kann einige Minuten dauern)..."
    apt-get "${APT_OPTS[@]}" update -qq
    # confdef/confold: lokal angepasste Konfiguration bei Updates behalten.
    apt-get "${APT_OPTS[@]}" install -y -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold "${deb}"
}

# --- Andere Distributionen: Dateien direkt installieren ----------------------

python_ok() {
    local candidate
    for candidate in python3 python3.13 python3.12 python3.11 python3.10; do
        command -v "${candidate}" >/dev/null 2>&1 && \
            "${candidate}" -c 'import sys, venv, ensurepip; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null && return 0
    done
    return 1
}

install_dependencies() {
    log "Installiere Abhängigkeiten über ${PM}..."
    case "${PM}" in
        dnf)
            # curl nicht explizit anfordern: RHEL-Klone bringen oft curl-minimal mit,
            # das mit dem Paket "curl" kollidiert. Fehlt curl ganz, holt ensure_curl es.
            dnf install -y python3 NetworkManager NetworkManager-wifi dnsmasq avahi iw iproute ca-certificates polkit findutils shadow-utils util-linux
            ensure_curl
            python_ok || dnf install -y python3.12 || dnf install -y python3.11
            ;;
        pacman)
            pacman -Syu --needed --noconfirm python networkmanager dnsmasq avahi iw iproute2 curl ca-certificates polkit findutils
            ;;
        zypper)
            zypper --non-interactive install python3 python3-pip NetworkManager dnsmasq avahi iw iproute2 curl ca-certificates polkit findutils shadow util-linux
            python_ok || zypper --non-interactive install python312 python312-pip || zypper --non-interactive install python311 python311-pip
            ;;
    esac
    python_ok || fail "Python 3.10 oder neuer (mit venv/ensurepip) konnte nicht installiert werden."
}

install_generic() {
    local src root
    if [[ -n "${PROJECT_DIR}" ]]; then
        src="${PROJECT_DIR}"
        log "Projektordner gefunden: installiere aus ${src}"
    else
        download "$(release_url "${PKG_NAME}_@V@_src.tar.gz")" "${WORK_DIR}/src.tar.gz"
        tar -xzf "${WORK_DIR}/src.tar.gz" -C "${WORK_DIR}"
        src="${WORK_DIR}/${PKG_NAME}"
        [[ -f "${src}/installer/stage.sh" ]] || fail "Quellarchiv unvollständig."
    fi

    install_dependencies

    local version
    version="$(sed -n 's/^version[[:space:]]*=[[:space:]]*"\(.*\)"/\1/p' "${src}/pyproject.toml" | head -n1)"
    # shellcheck source=installer/stage.sh
    . "${src}/installer/stage.sh"
    root="${WORK_DIR}/root"
    stage_files "${src}" "${root}" "${UNIT_DIR}" "${version}"

    # Lokal angepasste Konfiguration bei Updates nicht überschreiben.
    if [[ -f /etc/autodarts-headless-control.env ]]; then
        rm -f "${root}/etc/autodarts-headless-control.env"
    fi

    systemctl stop autodarts-headless-control.service 2>/dev/null || true
    rm -rf "/opt/${PKG_NAME}/app"
    # Datei für Datei installieren: Zielverzeichnisse können Symlinks sein
    # (z. B. /usr/local/sbin -> bin auf Fedora), die "cp -a" nicht überschreiben kann.
    local file
    while IFS= read -r file; do
        install -D -m "$(stat -c '%a' "${root}/${file}")" "${root}/${file}" "/${file}"
    done < <(cd "${root}" && find . -type f | sed 's|^\./||')

    mkdir -p "$(dirname "${MANIFEST}")"
    (cd "${root}" && find . -type f | sed 's|^\.||' | sort) > "${MANIFEST}"
    grep -qx "/etc/autodarts-headless-control.env" "${MANIFEST}" || echo "/etc/autodarts-headless-control.env" >> "${MANIFEST}"

    log "Richte das System ein (Benutzer, Python-Umgebung, Firewall, Autodarts)..."
    "/opt/${PKG_NAME}/installer/setup.sh" configure --mode generic
}

uninstall_generic() {
    [[ -f "${MANIFEST}" ]] || fail "Keine Installation gefunden (${MANIFEST} fehlt)."
    systemctl disable --now autodarts-headless-control.service autodarts-update.timer \
        autodarts-headless-control-update.timer 2>/dev/null || true
    while IFS= read -r file; do
        [[ -n "${file}" ]] && rm -f "${file}"
    done < "${MANIFEST}"
    rm -rf "/opt/${PKG_NAME}" "$(dirname "${MANIFEST}")" /var/lib/autodarts-headless-control-firewall
    systemctl daemon-reload 2>/dev/null || true
    log "Entfernt. Autodarts und die Board-Kalibrierung unter /var/lib/autodarts-headless-control bleiben erhalten."
}

# --- Ablauf -----------------------------------------------------------------

if [[ "${ACTION}" == "uninstall" ]]; then
    if [[ "${PM}" == "apt" ]] && dpkg -s "${PKG_NAME}" >/dev/null 2>&1; then
        apt-get purge -y "${PKG_NAME}"
    else
        uninstall_generic
    fi
    exit 0
fi

if [[ "${PM}" == "apt" ]]; then
    install_deb
else
    install_generic
fi

check_network_management

echo
log "Installation abgeschlossen."
log "Bitte einmal neu starten:  sudo reboot"
log "Danach im Browser öffnen:  http://autodarts.local"
log "Dort 'Board einrichten (Board-Manager)' wählen – Autodarts startet automatisch im Hintergrund."
