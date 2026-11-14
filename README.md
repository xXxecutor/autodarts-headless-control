# Autodarts Headless Control

Zuverlässige, browserbasierte Steuerung für Autodarts auf Linux-Mini-PCs und Single-Board-Computern (Raspberry Pi, x86_64, ARM64). Ermöglicht den headless Betrieb ohne angeschlossenen Monitor oder Tastatur.

---

## ✨ Funktionen im Überblick

### 🎯 Für den Alltag am Dartboard (Endnutzer)
- **Einschalten & Loswerfen (Echter Headless-Betrieb):** Kein Monitor, keine Tastatur nötig. Das System startet nach dem Einschalten vollautomatisch im Hintergrund und lässt sich bequem über jedes Smartphone, Tablet oder jeden PC im Browser unter `http://autodarts.local` steuern.
- **Board-Einrichtung direkt im Browser:** Kameras zuordnen, Bildeinstellungen anpassen und das Board kalibrieren erfolgt im offiziellen Autodarts **Board-Manager** (ab Autodarts 2.1), der mit einem Klick von der Startseite geöffnet wird – ganz ohne Monitor, Tastatur oder Konsole. Für ältere Autodarts-Versionen steht die Terminal-Einrichtung (TUI) als Fallback bereit.
- **Autostart ohne Zutun:** Autodarts wird automatisch als Hintergrunddienst eingerichtet und läuft nach jedem Einschalten – kein Häkchen in der TUI, keine Konsole nötig.
- **Direkt zum Spiel (play.autodarts.com):** Mit nur einem Klick direkt zur offiziellen Autodarts-Spielplattform wechseln und das Match starten.
- **Kinderleichte WLAN-Verbindung:** Umgebende Netzwerke direkt im Browser scannen, WLAN auswählen, Passwort eingeben – fertig verbunden.
- **Automatischer Setup-Hotspot (Fallback):** Ist kein bekanntes WLAN in Reichweite (z. B. an einem neuen Spielort), spannt das Gerät automatisch einen eigenen WLAN-Hotspot auf (`Autodarts-Setup`), damit das neue Heimnetz bequem konfiguriert werden kann.
- **Sicheres Ausschalten & Neustarten:** System direkt über die Web-Oberfläche herunterfahren oder neu starten – schützt die SD-Karte oder SSD zuverlässig vor Datenverlust durch Steckerziehen.

### 🛠️ Für Vorbereiter, Admins & Tüftler (Technik & System)
- **Übergabe-Modus (Handover):** Box für Freunde oder Vereinskollegen komplett vorbereiten und testen; vor der Weitergabe löscht ein Klick alle privaten WLAN-Passwörter, behält aber die Autodarts-Installation und Board-Kalibrierung geschützt bei.
- **Integrierter Protokoll-Viewer:** Logs von Headless Control, Firewall & Netzwerk-Dispatcher, Autodarts-Dienst sowie System-Warnungen direkt im Browser prüfen – zur schnellen Fehlerdiagnose ohne Konsole.
- **Ethernet-Priorität & Firewall-Schutz:** Kabelgebundene Netzwerkverbindungen haben immer Vorrang und werden nie durch WLAN-Aktionen unterbrochen. Mit `ufw` werden die Freigaben dynamisch pro Netzwerk-Schnittstelle und Subnetz gesetzt; bei `firewalld` (Fedora, openSUSE) werden die nötigen Ports freigegeben.
- **Sicherer Betrieb ohne Root-Passwort:** Der Dienst läuft unter einem isolierten Systembenutzer (`autodarts`) und nutzt Polkit/D-Bus für privilegierte Aktionen ohne SUID-Bit oder Root-Rechte.

---

## 🚀 Schnellanleitung & Benutzerrollen

Das ausführliche Schritt-für-Schritt-Handbuch findest du in der **[Benutzeranleitung (docs/USER_GUIDE.md)](docs/USER_GUIDE.md)**. Es deckt drei typische Rollen ab:

* **🎯 1. Empfänger (Fertige Box erhalten):** Strom anschließen. Bei LAN sofort loslegen; bei WLAN mit dem Hotspot `Autodarts-Setup` (PW: `autodarts123`) verbinden, unter `http://autodarts.local` das Heim-WLAN auswählen und spielen.
* **🛠️ 2. Selbsteinrichter (Eigenes Gerät aufbauen):** Ein 64-Bit-Linux installieren (z. B. Raspberry Pi OS, Debian, Ubuntu, Fedora, Arch oder openSUSE), den Installations-Einzeiler ausführen, neu starten und das Board im Board-Manager einrichten.
* **🎁 3. Vorbereiter (Box für Freunde einrichten):** System komplett vorbereiten und testen, dann unter `http://autodarts.local/admin` im Bereich **„Gerät übergeben“** auf **„WLAN-Zugangsdaten löschen“** klicken (löscht private WLAN-Passwörter, behält aber die Autodarts-Installation und Board-Kalibrierung), herunterfahren und übergeben.

---

## Unterstützte Linux-Distributionen & Systemvoraussetzungen

Autodarts Headless Control läuft auf praktisch jedem aktuellen 64-Bit-Linux mit systemd – auf Mini-PCs (x86_64) ebenso wie auf ARM-Boards wie dem Raspberry Pi 4/5 (ARM64). Der Installer erkennt die Distribution und nutzt deren Paketverwaltung:

| Distributionsfamilie | Getestete Versionen | Installation über |
|---|---|---|
| **Raspberry Pi OS** (64-Bit) | Bookworm und neuer | `.deb`-Paket (apt) |
| **Debian** | 12 (Bookworm), 13 (Trixie) | `.deb`-Paket (apt) |
| **Ubuntu** und Varianten (Kubuntu, Xubuntu, …) | 22.04 LTS, 24.04 LTS | `.deb`-Paket (apt) |
| Linux Mint, LMDE, Pop!_OS, Zorin OS, Q4OS, DietPi | auf Basis der obigen Versionen | `.deb`-Paket (apt) |
| **Fedora** | aktuelle Version | Dateien + `dnf` |
| AlmaLinux, Rocky Linux, RHEL | 9 | Dateien + `dnf` |
| **Arch Linux**, Manjaro, EndeavourOS | Rolling Release | Dateien + `pacman` |
| **openSUSE** | Tumbleweed, Leap 15.6 | Dateien + `zypper` |

„Getestet“ bedeutet: Installation, Start der Weboberfläche, Update und Deinstallation laufen bei jeder Änderung automatisch in der CI ([GitHub Actions](.github/workflows/ci.yml)). WLAN, Hotspot und Kameras lassen sich dort nicht prüfen – sie hängen vor allem von NetworkManager und der Hardware ab.

### Auf echter Hardware geprüft

| Gerät | System | Geprüft |
|---|---|---|
| HP t630 Thin Client (AMD, x86_64) | Debian 13 (Trixie) | Installation per Einzeiler, Autodarts-Autostart, Weboberfläche und Board-Manager über LAN und WLAN, Neustarts |
| Raspberry Pi 4 Model B (ARM64) | Raspberry Pi OS 64-Bit (Trixie) | wie oben, dazu Setup-Hotspot mit einem Android-Handy und „Gerät übergeben“ |

Noch nicht auf echter Hardware geprüft: Ubuntu, Fedora, Arch und openSUSE (nur in der CI), die Einrichtung über den Setup-Hotspot mit einem iPhone sowie Kameras und Kalibrierung. Erfahrungsberichte – auch „läuft“ – gern als [Issue](https://github.com/xXxecutor/autodarts-headless-control/issues).

> **Hinweis:** Autodarts selbst gibt es nur für 64-Bit-Systeme (x86_64 und ARM64). Auf einem Raspberry Pi daher unbedingt die 64-Bit-Variante von Raspberry Pi OS verwenden.

### Systemvoraussetzungen

Die Abhängigkeiten installiert der Installer automatisch:

- **Init-System:** `systemd` (Dienste, `journalctl`, `systemd-logind`)
- **Netzwerk:** `NetworkManager` verwaltet das WLAN (Voraussetzung für WLAN-Einrichtung und Setup-Hotspot). Bei Raspberry Pi OS, Fedora und Desktop-Varianten ist das Standard. Bei Server-Installationen übernimmt der Installer bestehende WLAN-Zugangsdaten automatisch – aus `/etc/network/interfaces` (Debian) bzw. Netplan (Ubuntu Server) – wirksam nach dem Neustart. Nur bei Sonderfällen (WLAN mit fester IP-Adresse, `iwd`/`wicked`/`systemd-networkd` auf Arch oder openSUSE) gibt er stattdessen einen Hinweis; LAN und alle übrigen Funktionen laufen auch dann.
- **WLAN-Karte für den Setup-Hotspot:** Der Hotspot braucht eine WLAN-Karte mit Access-Point-Modus. Die eingebauten Karten des Raspberry Pi 4/5 und viele Intel- und Realtek-Karten können das, manche USB-WLAN-Sticks nicht. Prüfen lässt es sich mit `iw list` – unter „Supported interface modes“ muss `AP` stehen. Ohne AP-Modus funktioniert alles andere weiterhin; die erste WLAN-Einrichtung erfolgt dann per LAN-Kabel über die Admin-Seite.
- **Firewall:** `ufw` (Debian/Ubuntu, wird mitinstalliert) oder ein bereits aktives `firewalld` (Fedora, openSUSE, RHEL). Ohne Firewall (z. B. Arch-Standard) sind keine Regeln nötig.
- **Namensauflösung:** `avahi-daemon` für `http://autodarts.local`
- **Berechtigungen:** `polkit` für WLAN-Verwaltung, Neustart und Herunterfahren ohne Passwort
- **Laufzeitumgebung:** Python 3.10 oder neuer (bei Bedarf installiert der Installer eine neuere Version, z. B. auf AlmaLinux 9 oder openSUSE Leap)

---

## Installation & Einrichtung

### Empfohlen: Ein Befehl

Auf dem frisch installierten Linux-Gerät (mit Internetverbindung) im Terminal oder per SSH:

```bash
curl -fsSL https://github.com/xXxecutor/autodarts-headless-control/releases/latest/download/install.sh | sudo bash
```

Danach einmal neu starten (`sudo reboot`) und im Browser `http://autodarts.local` öffnen. Mehr ist nicht nötig. Git wird nicht benötigt.

<details>
<summary>Kein <code>curl</code> oder kein <code>sudo</code> vorhanden (z. B. minimales Debian)?</summary>

```bash
wget -qO- https://github.com/xXxecutor/autodarts-headless-control/releases/latest/download/install.sh | sudo bash
```

Ohne `sudo` (Debian, wenn bei der Installation ein root-Passwort vergeben wurde):

```bash
su -c "wget -qO- https://github.com/xXxecutor/autodarts-headless-control/releases/latest/download/install.sh | bash"
```
</details>

Der Installer lädt die neueste Version aus den [GitHub-Releases](https://github.com/xXxecutor/autodarts-headless-control/releases/latest) und erledigt alles Weitere selbst:

1. Systempakete installieren (NetworkManager, Avahi, polkit, `iw`, Firewall, …) – über `apt`, `dnf`, `pacman` oder `zypper`
2. Dienstbenutzer `autodarts` anlegen (inkl. Kamerazugriff und Start ohne Anmeldung)
3. Anwendung unter `/opt/autodarts-headless-control` mit eigener Python-Umgebung einrichten
4. `autodarts.local`, polkit-Rechte (WLAN, Neustart, Herunterfahren ohne Passwort) und Firewall konfigurieren
5. Autodarts (headless) installieren – der Autostart als Hintergrunddienst wird beim ersten Start automatisch eingerichtet
6. Bestehende WLAN-Konfigurationen an NetworkManager übergeben (falls nötig) und bei belegtem Port 80 auf Port 8080 ausweichen
7. Weboberfläche sowie die automatischen Updates für Autodarts und Headless Control aktivieren

Auf Debian, Ubuntu, Raspberry Pi OS und deren Ablegern geschieht das über ein echtes `.deb`-Paket; auf allen anderen Distributionen werden dieselben Dateien direkt installiert.

Optionen (an `sudo bash -s --` anhängen, z. B. `… | sudo bash -s -- --beta`):

| Option | Wirkung |
|---|---|
| `--version 1.2.0` | bestimmte Version statt der neuesten installieren |
| `--beta` | Autodarts-Beta statt der stabilen Version installieren |
| `--skip-autodarts` | nur Headless Control installieren, Autodarts nicht |
| `--uninstall` | Headless Control entfernen |

**Updates laufen automatisch:** Jede Nacht sucht jedes Gerät nach einer neuen Version von Headless Control und von Autodarts und installiert sie selbstständig. Niemand muss dafür etwas tun. Lokale Anpassungen in `/etc/autodarts-headless-control.env` bleiben erhalten. Ein- und ausschalten lassen sich die Updates (Headless Control und Autodarts) in der Admin-Oberfläche unter „System“ → „Automatische Updates“; dort steht auch die installierte Version. Fest abschalten lassen sich die Updates von Headless Control mit `HEADLESS_AUTO_UPDATE=0` in der Konfigurationsdatei – der Schalter ist dann gesperrt.

### Alternative: Paket manuell herunterladen (Debian/Ubuntu/Raspberry Pi OS)

Die Datei `autodarts-headless-control_<Version>_all.deb` aus den [Releases](https://github.com/xXxecutor/autodarts-headless-control/releases) laden (z. B. per USB-Stick übertragen) und installieren:

```bash
sudo apt install ./autodarts-headless-control_<Version>_all.deb
```

### Alternative: Aus dem Quellcode

Aus einem Git-Checkout oder entpackten ZIP-Download installiert der Installer direkt die vorliegende Version:

```bash
git clone https://github.com/xXxecutor/autodarts-headless-control.git
cd autodarts-headless-control
sudo ./installer/install.sh
```

Nur das `.deb`-Paket bauen (z. B. zum Verteilen): `./installer/build-deb.sh` → `dist/`.

### Deinstallation

```bash
curl -fsSL https://github.com/xXxecutor/autodarts-headless-control/releases/latest/download/install.sh | sudo bash -s -- --uninstall
```

(Auf Debian/Ubuntu alternativ `sudo apt purge autodarts-headless-control`.) Die Autodarts-Installation und Board-Kalibrierung unter `/var/lib/autodarts-headless-control` bleiben dabei erhalten.

### Konfiguration

Die Betriebsparameter werden über `/etc/autodarts-headless-control.env` gesteuert:

```env
AUTODARTS_USER=autodarts
AUTODARTS_HOME=/var/lib/autodarts-headless-control
AUTODARTS_EXECUTABLE=
HEADLESS_HTTP_PORT=80
HEADLESS_WS_PORT=8092
```

Optionale Werte für den automatischen Setup-Hotspot (Standardwerte in Klammern):

| Variable | Bedeutung |
|---|---|
| `HEADLESS_HOTSPOT_FALLBACK` (`1`) | `0` deaktiviert den automatischen Hotspot |
| `HEADLESS_HOTSPOT_GRACE` (`45`) | Sekunden ohne Ethernet/WLAN, bevor der Hotspot startet |
| `HEADLESS_HOTSPOT_RETRY` (`300`) | Läuft der Hotspot so lange ohne verbundenes Gerät, wird das gespeicherte Heim-WLAN erneut versucht |
| `HEADLESS_AUTODARTS_AUTOSTART` (`1`) | `0` verhindert, dass Autodarts automatisch als Hintergrunddienst eingerichtet wird |
| `HEADLESS_AUTO_UPDATE` (`1`) | `0` schaltet die automatischen Updates von Headless Control ab |

Ist Port 80 bei der Installation bereits von einem anderen Dienst belegt (z. B. einem Webserver), stellt der Installer automatisch auf `HEADLESS_HTTP_PORT=8080` um; die Oberfläche ist dann unter `http://autodarts.local:8080` erreichbar.

---

## Lokale Entwicklung & Tests

Entwicklungsumgebung einrichten:

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
```

Testsuite ausführen:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Anwendung lokal starten (ohne Root auf einem freien Port):

```bash
HEADLESS_HTTP_PORT=8080 .venv/bin/python -m app.main
```

### Continuous Integration & Releases

GitHub Actions ([`.github/workflows`](.github/workflows)) prüft jeden Push auf echtem Linux:

- Unit-Tests mit Python 3.10 bis 3.13 (inkl. Firewall-Skripte und Pseudoterminal)
- Shell-Skripte (`bash -n`, `shellcheck`)
- Bau des `.deb`-Pakets und Test-Installation in Debian 12/13 und Ubuntu 22.04/24.04 – inklusive Start der Weboberfläche und echter Autodarts-Installation (Debian 12)
- Installation, Update und Deinstallation ohne apt in Fedora, AlmaLinux 9, Arch Linux, openSUSE Tumbleweed und Leap 15.6
- Echter Systemstart auf einer Ubuntu-VM mit systemd: gehärteter Dienst, polkit-Rechte, automatischer Autodarts-Dienst, „Autodarts neu starten“ und Selbst-Update

### Neue Version veröffentlichen

Änderungen committen und pushen, dann einen Versions-Tag setzen – mehr ist nicht zu tun:

```bash
git tag v1.1.0
git push origin v1.1.0
```

Der Release-Workflow testet, baut `.deb`, Quellarchiv und `install.sh` und veröffentlicht sie als GitHub-Release (die Version kommt allein aus dem Tag). Alle installierten Geräte übernehmen die neue Version innerhalb eines Tages automatisch. Tags mit Bindestrich (z. B. `v1.1.0-beta1`) werden als Vorabversion veröffentlicht und nicht automatisch verteilt.

## Lizenz

Autodarts Headless Control steht unter der [PolyForm Noncommercial License 1.0.0](LICENSE.md).

- ✅ Nutzen, forken, anpassen und weitergeben – privat, im Verein, in Schulen und anderen nicht kommerziellen Einrichtungen
- ✅ Eigene Varianten veröffentlichen, solange sie ebenfalls nicht kommerziell genutzt werden
- ❌ Kommerzielle Nutzung (z. B. Verkauf, Einbau in kommerzielle Produkte oder bezahlte Dienstleistungen)
- 📌 Bei Weitergabe die Lizenz und die Zeile `Required Notice: …` aus [`LICENSE.md`](LICENSE.md) beibehalten – so bleibt die Herkunft erkennbar

Für eine kommerzielle Nutzung bitte vorher über ein [GitHub-Issue](https://github.com/xXxecutor/autodarts-headless-control/issues) Kontakt aufnehmen.

Mitgelieferte Fremdkomponenten behalten ihre eigene Lizenz: xterm.js steht unter der MIT-Lizenz ([`app/web/xterm.LICENSE`](app/web/xterm.LICENSE)). Autodarts selbst ist nicht Teil dieses Projekts und wird direkt vom Hersteller installiert.
