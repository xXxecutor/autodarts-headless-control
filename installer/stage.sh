#!/usr/bin/env bash
# Autodarts Headless Control – gemeinsame Dateiliste
#
# Wird von build-deb.sh (Debian-Paket) und install.sh (andere Distributionen)
# eingebunden, damit beide Wege exakt dieselben Dateien installieren.
#
#   stage_files <PROJECT_DIR> <ROOT> <UNIT_DIR> <VERSION>
#
# UNIT_DIR ist das systemd-Verzeichnis relativ zu ROOT, z. B. "lib/systemd/system"
# (Paket) oder "usr/local/lib/systemd/system" (Installation ohne Paketverwaltung).

PKG_NAME="autodarts-headless-control"

stage_files() {
    local project="$1" root="$2" unit_dir="$3" version="$4"
    local app_dir="${root}/opt/${PKG_NAME}"

    mkdir -p "${app_dir}/installer" \
        "${root}/etc/avahi/services" \
        "${root}/etc/NetworkManager/dispatcher.d" \
        "${root}/etc/NetworkManager/dnsmasq-shared.d"         "${root}/etc/network/if-up.d"         "${root}/etc/network/if-post-down.d" \
        "${root}/etc/polkit-1/rules.d" \
        "${root}/etc/polkit-1/localauthority/50-local.d" \
        "${root}/etc/sudoers.d" \
        "${root}/${unit_dir}" \
        "${root}/usr/local/sbin"

    # Anwendung
    cp -r "${project}/app" "${app_dir}/"
    cp "${project}/pyproject.toml" "${project}/README.md" "${project}/LICENSE.md" "${app_dir}/"
    install -m 0755 "${project}/installer/setup.sh"           "${app_dir}/installer/setup.sh"
    install -m 0755 "${project}/installer/self-update.sh"     "${app_dir}/installer/self-update.sh"
    install -m 0755 "${project}/installer/migrate-network.py" "${app_dir}/installer/migrate-network.py"
    find "${app_dir}" \( -name '__pycache__' -o -name '*.pyc' -o -name '*.bak' -o -name '*.save' \) -prune -exec rm -rf {} +
    sed -i "s/^version[[:space:]]*=.*/version = \"${version}\"/" "${app_dir}/pyproject.toml"

    # Systemdateien
    install -m 0640 "${project}/packaging/etc/autodarts-headless-control.env"   "${root}/etc/autodarts-headless-control.env"
    install -m 0644 "${project}/packaging/avahi/autodarts.service"              "${root}/etc/avahi/services/autodarts.service"
    install -m 0644 "${project}/packaging/polkit/99-autodarts-network.rules"     "${root}/etc/polkit-1/rules.d/99-autodarts-network.rules"
    install -m 0644 "${project}/packaging/polkit/99-autodarts-network.pkla"      "${root}/etc/polkit-1/localauthority/50-local.d/99-autodarts-network.pkla"
    install -m 0440 "${project}/packaging/sudoers/headless-control"              "${root}/etc/sudoers.d/headless-control"
    install -m 0644 "${project}/packaging/systemd/"*.service "${project}/packaging/systemd/"*.timer "${root}/${unit_dir}/"
    install -m 0750 "${project}/installer/90-autodarts-firewall"                 "${root}/etc/NetworkManager/dispatcher.d/90-autodarts-firewall"
    install -m 0755 "${project}/installer/ifupdown-autodarts-firewall"          "${root}/etc/network/if-up.d/autodarts-firewall"
    install -m 0755 "${project}/installer/ifupdown-autodarts-firewall"          "${root}/etc/network/if-post-down.d/autodarts-firewall"
    install -m 0644 "${project}/installer/dnsmasq-shared-autodarts.conf"         "${root}/etc/NetworkManager/dnsmasq-shared.d/autodarts.conf"
    install -m 0750 "${project}/installer/autodarts-firewall-sync"               "${root}/usr/local/sbin/autodarts-firewall-sync"

    # Windows-Zeilenenden (z. B. aus einem ZIP-Download) würden Skripte unbrauchbar machen.
    find "${root}/etc" "${root}/${unit_dir}" "${root}/usr/local/sbin" "${app_dir}/installer" \
        -type f -exec sed -i 's/\r$//' {} +
}
