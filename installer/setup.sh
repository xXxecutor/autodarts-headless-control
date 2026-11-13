#!/usr/bin/env bash
# Autodarts Headless Control – Systemeinrichtung
#
# Wird nach dem Kopieren der Programmdateien ausgeführt:
#   - vom Debian-Paket (postinst):              setup.sh configure --mode deb
#   - von install.sh auf anderen Distributionen: setup.sh configure --mode generic
#
# Optionale Umgebungsvariablen:
#   AUTODARTS_HEADLESS_SKIP_AUTODARTS=1   Autodarts selbst nicht installieren
#   AUTODARTS_VERSION=beta                Autodarts-Beta statt stabiler Version
#   PYTHON=/usr/bin/python3.12            bestimmten Python-Interpreter verwenden

set -e

APP_USER="autodarts"
APP_HOME="/var/lib/autodarts-headless-control"
INSTALL_DIR="/opt/autodarts-headless-control"
ENV_FILE="/etc/autodarts-headless-control.env"
UNITS="autodarts-headless-control.service autodarts-update.service autodarts-update.timer autodarts-headless-control-update.service autodarts-headless-control-update.timer"

log() { echo "[autodarts-headless-control] $*"; }
systemd_running() { [ -d /run/systemd/system ]; }

find_python() {
    local candidate
    if [ -n "${PYTHON:-}" ]; then
        echo "${PYTHON}"
        return 0
    fi
    for candidate in python3 python3.13 python3.12 python3.11 python3.10; do
        if command -v "${candidate}" >/dev/null 2>&1 && \
            "${candidate}" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
            command -v "${candidate}"
            return 0
        fi
    done
    return 1
}

migrate_legacy_units() {
    # Frühere Versionen von install.sh haben Units direkt nach /etc/systemd/system
    # geschrieben. Diese würden die Units aus dem Paket überdecken.
    local unit path
    for unit in ${UNITS}; do
        path="/etc/systemd/system/${unit}"
        if [ -f "${path}" ] && [ ! -L "${path}" ] && ! dpkg -S "${path}" >/dev/null 2>&1; then
            mv -f "${path}" "${path}.autodarts-old"
            log "Veraltete Unit ${path} nach ${path}.autodarts-old verschoben."
        fi
    done
}

env_value() {
    # Wert aus der Konfigurationsdatei lesen (ohne sie als Shell-Skript auszuführen)
    sed -n "s/^[[:space:]]*$1[[:space:]]*=[[:space:]]*//p" "${ENV_FILE}" 2>/dev/null | tail -n1 | tr -d '"'"'"
}

set_env_value() {
    if grep -q "^[[:space:]]*$1[[:space:]]*=" "${ENV_FILE}"; then
        sed -i "s|^[[:space:]]*$1[[:space:]]*=.*|$1=$2|" "${ENV_FILE}"
    else
        echo "$1=$2" >> "${ENV_FILE}"
    fi
}

port_in_use() {
    command -v ss >/dev/null 2>&1 || return 1
    [ -n "$(ss -Hltn "sport = :$1" 2>/dev/null)" ]
}

configure_ports() {
    # Belegt bereits ein anderer Dienst Port 80 (z. B. ein Webserver), weicht die
    # Weboberfläche auf 8080 aus, statt beim Start dauerhaft zu scheitern.
    local http_port
    http_port="$(env_value HEADLESS_HTTP_PORT)"
    http_port="${http_port:-80}"
    if systemd_running; then
        systemctl stop autodarts-headless-control.service 2>/dev/null || true
    fi
    if [ "${http_port}" = "80" ] && port_in_use 80; then
        set_env_value HEADLESS_HTTP_PORT 8080
        http_port=8080
        log "HINWEIS: Port 80 ist belegt – Weboberfläche nutzt http://autodarts.local:8080"
    fi
    # mDNS-Dienstanzeige an den tatsächlichen Port anpassen
    sed -i "s|<port>[0-9]*</port>|<port>${http_port}</port>|" /etc/avahi/services/autodarts.service 2>/dev/null || true
}

configure_network_manager() {
    # WLAN-Einrichtung und Setup-Hotspot setzen voraus, dass NetworkManager das WLAN
    # verwaltet. Bestehende WLAN-Konfigurationen werden übernommen; wirksam wird das
    # beim nächsten Neustart, eine laufende (SSH-)Verbindung bleibt also bestehen.
    local output svc competing=""
    [ "${AUTODARTS_HEADLESS_KEEP_NETWORK:-0}" = "1" ] && return 0
    command -v nmcli >/dev/null 2>&1 || return 0

    output="$("${INSTALL_DIR}/.venv/bin/python" "${INSTALL_DIR}/installer/migrate-network.py" 2>&1 || true)"
    if [ -n "${output}" ]; then
        printf '%s\n' "${output}" | grep -v '^NETPLAN_SWITCHED$' | while IFS= read -r line; do log "${line}"; done
    fi
    if printf '%s' "${output}" | grep -q '^NETPLAN_SWITCHED$' && systemd_running; then
        # Ohne von networkd verwaltete Verbindungen würde dessen Online-Warten den Boot bremsen.
        systemctl disable systemd-networkd-wait-online.service >/dev/null 2>&1 || true
        systemctl enable NetworkManager-wait-online.service >/dev/null 2>&1 || true
    fi

    # NetworkManager für den nächsten Boot aktivieren, sofern kein anderer
    # Netzwerkdienst aktiv ist (sonst würden sich beide in die Quere kommen).
    if systemd_running && ! systemctl is-enabled --quiet NetworkManager.service 2>/dev/null; then
        for svc in systemd-networkd iwd wicked connman netctl dhcpcd; do
            systemctl is-active --quiet "${svc}.service" 2>/dev/null && competing="${competing} ${svc}"
        done
        if [ -z "${competing}" ]; then
            systemctl enable NetworkManager.service >/dev/null 2>&1 || true
            log "NetworkManager für den nächsten Start aktiviert."
        else
            log "HINWEIS: Netzwerk wird von${competing} verwaltet. Für WLAN-Einrichtung und Hotspot"
            log "         stattdessen NetworkManager aktivieren (siehe Dokumentation)."
        fi
    fi
}

configure_firewall() {
    if command -v ufw >/dev/null 2>&1; then
        # Alles eingehend sperren außer SSH; Autodarts-Zugänge gibt
        # autodarts-firewall-sync je nach aktivem Netz dynamisch frei.
        ufw default deny incoming >/dev/null 2>&1 || true
        ufw default allow outgoing >/dev/null 2>&1 || true
        ufw allow 22/tcp comment 'SSH' >/dev/null 2>&1 || true
        ufw --force enable >/dev/null 2>&1 || true
        /usr/local/sbin/autodarts-firewall-sync >/dev/null 2>&1 || true
        log "Firewall: ufw (dynamische Freigaben je Netzwerk)."
    elif command -v firewall-cmd >/dev/null 2>&1 && firewall-cmd --state >/dev/null 2>&1; then
        # Fedora, openSUSE, RHEL & Co.: Ports in der Standardzone und in der
        # Zone des NetworkManager-Hotspots (nm-shared) freigeben.
        local zone http_port ws_port
        http_port="$(env_value HEADLESS_HTTP_PORT)"; http_port="${http_port:-80}"
        ws_port="$(env_value HEADLESS_WS_PORT)"; ws_port="${ws_port:-8092}"
        for zone in "$(firewall-cmd --get-default-zone)" nm-shared; do
            firewall-cmd --permanent --zone="${zone}" --add-service=mdns \
                --add-port="${http_port}/tcp" --add-port="${ws_port}/tcp" --add-port=3180/tcp >/dev/null 2>&1 || true
        done
        firewall-cmd --reload >/dev/null 2>&1 || true
        log "Firewall: firewalld (Ports ${http_port}, ${ws_port}, 3180 und mDNS freigegeben)."
    else
        log "Firewall: keine aktive Firewall erkannt (ufw/firewalld) – keine Regeln nötig."
    fi
}

install_autodarts() {
    local bin="${APP_HOME}/.local/bin/autodarts" extra=""
    if [ "${AUTODARTS_HEADLESS_SKIP_AUTODARTS:-0}" = "1" ]; then
        log "Autodarts-Installation übersprungen (AUTODARTS_HEADLESS_SKIP_AUTODARTS=1)."
        return 0
    fi
    [ -x "${bin}" ] && return 0
    log "Installiere Autodarts (headless)..."
    [ "${AUTODARTS_VERSION:-}" = "beta" ] && extra="--beta"
    if ! runuser -u "${APP_USER}" -- env HOME="${APP_HOME}" bash -c \
        "curl -fsSL https://autodarts.sh | bash -s -- --headless ${extra}"; then
        log "WARNUNG: Autodarts konnte nicht installiert werden."
        log "Erneut versuchen: sudo ${INSTALL_DIR}/installer/setup.sh configure"
    fi
}

configure() {
    local mode="$1" python nologin

    # 1. Dienstbenutzer
    nologin="$(command -v nologin || echo /usr/sbin/nologin)"
    if ! id -u "${APP_USER}" >/dev/null 2>&1; then
        useradd --system --home-dir "${APP_HOME}" --shell "${nologin}" "${APP_USER}"
    fi
    # Logs im Browser (journalctl) und Kamerazugriff: Ohne Login-Sitzung erhält
    # der Dienstbenutzer keine Geräte-ACLs für /dev/video*, darum Gruppe 'video'.
    getent group video >/dev/null 2>&1 || groupadd --system video 2>/dev/null || true
    usermod -aG systemd-journal "${APP_USER}" 2>/dev/null || true
    usermod -aG video "${APP_USER}" 2>/dev/null || true
    # User-Dienste (Autodarts) auch ohne Anmeldung beim Booten starten.
    loginctl enable-linger "${APP_USER}" 2>/dev/null || true

    mkdir -p "${APP_HOME}"
    chown "${APP_USER}:${APP_USER}" "${APP_HOME}"
    chmod 750 "${APP_HOME}"

    # 2. Python-Umgebung (Programmcode gehört root, der Dienst liest nur)
    python="$(find_python)" || { log "FEHLER: Python 3.10 oder neuer wird benötigt."; exit 1; }
    if [ ! -x "${INSTALL_DIR}/.venv/bin/python" ]; then
        "${python}" -m venv "${INSTALL_DIR}/.venv"
    fi
    if ! "${INSTALL_DIR}/.venv/bin/python" -m pip install --quiet --disable-pip-version-check -e "${INSTALL_DIR}"; then
        log "FEHLER: Python-Abhängigkeiten konnten nicht installiert werden. Besteht eine Internetverbindung?"
        exit 1
    fi
    chown -R root:root "${INSTALL_DIR}"

    # 3. Konfiguration lesbar für den Dienst
    chown root:"${APP_USER}" /etc/autodarts-headless-control.env
    chmod 640 /etc/autodarts-headless-control.env
    [ -d /etc/sudoers.d ] && chmod 0440 /etc/sudoers.d/headless-control 2>/dev/null || true

    # 4. Hostname für http://autodarts.local
    if [ "$(hostname 2>/dev/null)" != "autodarts" ]; then
        hostnamectl set-hostname autodarts 2>/dev/null || true
    fi
    if ! grep -q "^127.0.1.1[[:space:]]\+autodarts$" /etc/hosts 2>/dev/null; then
        sed -i '/^127.0.1.1/d' /etc/hosts || true
        echo "127.0.1.1 autodarts" >> /etc/hosts || true
    fi

    # 5. SELinux-Kontexte (Fedora, RHEL) für kopierte Dateien setzen
    if command -v restorecon >/dev/null 2>&1; then
        restorecon -R "${INSTALL_DIR}" /etc/NetworkManager /etc/polkit-1 /etc/avahi/services \
            /usr/local/sbin/autodarts-firewall-sync /usr/local/lib/systemd 2>/dev/null || true
    fi

    # 6. Ports, Netzwerkverwaltung, Firewall
    configure_ports
    configure_network_manager
    configure_firewall

    # 7. Autodarts
    install_autodarts

    # 8. systemd
    [ "${mode}" = "deb" ] && migrate_legacy_units
    if systemd_running; then
        systemctl daemon-reload
        # NetworkManager-Dispatcher (Firewall-Abgleich) ist z. B. auf Arch nicht aktiv.
        systemctl enable NetworkManager-dispatcher.service >/dev/null 2>&1 || true
        systemctl enable --now avahi-daemon.service >/dev/null 2>&1 || true
        systemctl try-restart avahi-daemon.service >/dev/null 2>&1 || true
        systemctl enable autodarts-headless-control.service >/dev/null 2>&1 || true
        systemctl enable --now autodarts-update.timer >/dev/null 2>&1 || true
        systemctl enable --now autodarts-headless-control-update.timer >/dev/null 2>&1 || true
        systemctl restart autodarts-headless-control.service || true
    else
        # z. B. Container/chroot: nur für den nächsten Boot aktivieren.
        systemctl enable autodarts-headless-control.service autodarts-update.timer \
            autodarts-headless-control-update.timer avahi-daemon.service >/dev/null 2>&1 || true
    fi

    local port url="http://autodarts.local"
    port="$(env_value HEADLESS_HTTP_PORT)"
    [ -n "${port}" ] && [ "${port}" != "80" ] && url="${url}:${port}"
    log "Fertig. Weboberfläche: ${url} (nach einem Neustart)."
}

case "${1:-}" in
    configure)
        mode="generic"
        if [ "${2:-}" = "--mode" ] && [ -n "${3:-}" ]; then
            mode="$3"
        fi
        configure "${mode}"
        ;;
    *)
        echo "Aufruf: $0 configure [--mode deb|generic]" >&2
        exit 2
        ;;
esac
