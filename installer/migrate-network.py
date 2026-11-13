#!/usr/bin/env python3
"""Übergibt die WLAN-Verwaltung an NetworkManager (wirksam nach dem nächsten Neustart).

WLAN-Einrichtung und Setup-Hotspot funktionieren nur, wenn NetworkManager die
WLAN-Schnittstelle verwaltet. Server-Installationen konfigurieren WLAN aber oft
anders. Dieses Skript übernimmt bestehende WLAN-Zugangsdaten nach NetworkManager:

* Debian/ifupdown: WLAN-Abschnitte in /etc/network/interfaces werden als
  NetworkManager-Profil übernommen und dort auskommentiert (Sicherung *.autodarts-bak).
  Ethernet-Einträge bleiben unverändert.
* Netplan (Ubuntu Server): Sind WLANs mit systemd-networkd definiert, wird
  NetworkManager als Renderer gesetzt (/etc/netplan/99-autodarts-networkmanager.yaml).

Es wird nichts sofort umgeschaltet; eine laufende SSH-Verbindung bleibt bestehen.
Gelingt die Übernahme nicht, startet nach dem Neustart der Setup-Hotspot.

Ausgabe: eine Zeile pro Aktion, Rückgabewert 0 (auch wenn nichts zu tun war).
"""

import glob
import os
import re
import shutil
import sys
import uuid

INTERFACES = "/etc/network/interfaces"
NM_DIR = "/etc/NetworkManager/system-connections"
NETPLAN_DIR = "/etc/netplan"
NETPLAN_FILE = os.path.join(NETPLAN_DIR, "99-autodarts-networkmanager.yaml")
STANZA_START = ("iface", "auto", "allow-hotplug", "allow-auto", "mapping", "source", "source-directory")


def wireless_interfaces():
    return sorted(
        os.path.basename(p)
        for p in glob.glob("/sys/class/net/*")
        if os.path.isdir(os.path.join(p, "wireless"))
    )


def unquote(value):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def parse_wpa_conf(path):
    """Erstes network={...} aus einer wpa_supplicant-Konfiguration lesen."""
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return None
    match = re.search(r"network\s*=\s*\{(.*?)\}", text, re.S)
    if not match:
        return None
    fields = {}
    for line in match.group(1).splitlines():
        if "=" in line:
            key, val = line.strip().split("=", 1)
            fields[key.strip()] = val.strip()
    ssid = fields.get("ssid")
    if not ssid:
        return None
    psk = fields.get("psk")
    return {
        "ssid": unquote(ssid),
        "psk": unquote(psk) if psk else None,
        "open": fields.get("key_mgmt", "").upper() == "NONE",
    }


def keyfile_escape(value):
    return value.replace("\\", "\\\\").replace("\n", "\\n")


def write_nm_profile(ssid, psk, interface):
    os.makedirs(NM_DIR, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", ssid)[:40] or "wlan"
    name = f"autodarts-{ssid}"
    path = os.path.join(NM_DIR, f"autodarts-{safe}.nmconnection")
    lines = [
        "[connection]",
        f"id={keyfile_escape(name)}",
        f"uuid={uuid.uuid4()}",
        "type=wifi",
        "autoconnect=true",
        "",
        "[wifi]",
        "mode=infrastructure",
        f"ssid={keyfile_escape(ssid)}",
        "",
    ]
    if psk:
        lines += ["[wifi-security]", "key-mgmt=wpa-psk", f"psk={keyfile_escape(psk)}", ""]
    lines += ["[ipv4]", "method=auto", "", "[ipv6]", "method=auto", ""]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    os.chmod(path, 0o600)
    print(f"WLAN '{ssid}' ({interface}) als NetworkManager-Profil übernommen.")


def migrate_ifupdown(wifi):
    if not os.path.isfile(INTERFACES):
        return
    files = [INTERFACES] + sorted(glob.glob("/etc/network/interfaces.d/*"))
    for path in files:
        try:
            with open(path, encoding="utf-8") as fh:
                lines = fh.read().splitlines(keepends=True)
        except (OSError, UnicodeDecodeError):
            continue

        # Abschnitte je WLAN-Schnittstelle sammeln
        targets = {}  # Zeilenindex -> Schnittstelle
        current = None
        settings = {}
        for idx, line in enumerate(lines):
            stripped = line.strip()
            words = stripped.split()
            if words and words[0] in STANZA_START:
                current = None
                if words[0] in ("auto", "allow-hotplug", "allow-auto"):
                    for w in words[1:]:
                        if w in wifi:
                            targets[idx] = w
                elif words[0] == "iface" and len(words) >= 2 and words[1] in wifi:
                    current = words[1]
                    targets[idx] = current
                    settings.setdefault(current, {})["method"] = words[3] if len(words) > 3 else "dhcp"
                continue
            if current and stripped and not stripped.startswith("#"):
                targets[idx] = current
                key, _, val = stripped.partition(" ")
                settings[current][key] = val.strip()

        if not targets:
            continue

        migrated = set()
        for iface, cfg in settings.items():
            if cfg.get("method") not in ("dhcp", "auto", "manual"):
                print(f"WLAN {iface} nutzt eine feste IP-Adresse – bitte manuell an NetworkManager übergeben.")
                continue
            creds = None
            if cfg.get("wpa-ssid"):
                creds = {"ssid": unquote(cfg["wpa-ssid"]), "psk": unquote(cfg["wpa-psk"]) if cfg.get("wpa-psk") else None}
            elif cfg.get("wpa-conf"):
                creds = parse_wpa_conf(cfg["wpa-conf"])
            if creds:
                write_nm_profile(creds["ssid"], creds.get("psk"), iface)
            else:
                print(f"WLAN {iface}: keine Zugangsdaten gefunden – NetworkManager übernimmt die Schnittstelle ohne Profil.")
            migrated.add(iface)

        # auto/allow-hotplug-Zeilen ohne iface-Abschnitt ebenfalls freigeben
        migrated.update(i for i in targets.values() if i not in settings)

        if not migrated:
            continue
        backup = path + ".autodarts-bak"
        if not os.path.exists(backup):
            shutil.copy2(path, backup)
        new_lines = []
        for idx, line in enumerate(lines):
            if targets.get(idx) not in migrated or line.lstrip().startswith("#"):
                new_lines.append(line)
                continue
            words = line.split()
            if words and words[0] in ("auto", "allow-hotplug", "allow-auto"):
                # z. B. "auto lo wlan0": nur die WLAN-Schnittstelle entfernen
                rest = [w for w in words[1:] if w not in migrated]
                new_lines.append("# [autodarts: moved to NetworkManager] " + line)
                if rest:
                    new_lines.append(" ".join([words[0]] + rest) + "\n")
            else:
                new_lines.append("# [autodarts: moved to NetworkManager] " + line)
        with open(path, "w", encoding="utf-8") as fh:
            fh.writelines(new_lines)
        print(f"{path}: WLAN-Einträge auskommentiert (Sicherung: {backup}).")


def migrate_netplan():
    if not os.path.isdir(NETPLAN_DIR) or os.path.exists(NETPLAN_FILE):
        return False
    has_wifi = False
    renderer_nm = False
    for path in sorted(glob.glob(os.path.join(NETPLAN_DIR, "*.yaml"))):
        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            continue
        if re.search(r"^\s*wifis\s*:", text, re.M):
            has_wifi = True
        if re.search(r"renderer\s*:\s*NetworkManager", text):
            renderer_nm = True
    if not has_wifi or renderer_nm:
        return False
    with open(NETPLAN_FILE, "w", encoding="utf-8") as fh:
        fh.write(
            "# Autodarts Headless Control: WLAN-Einrichtung und Setup-Hotspot\n"
            "# benötigen NetworkManager als Netzwerkverwaltung.\n"
            "network:\n  version: 2\n  renderer: NetworkManager\n"
        )
    os.chmod(NETPLAN_FILE, 0o600)
    print(f"Netplan: NetworkManager als Renderer gesetzt ({NETPLAN_FILE}).")
    return True


def main():
    wifi = wireless_interfaces()
    if wifi:
        migrate_ifupdown(set(wifi))
    if migrate_netplan():
        print("NETPLAN_SWITCHED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
