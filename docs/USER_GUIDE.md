# Autodarts Headless Control – Benutzerhandbuch & Schnellanleitung

Dieses Handbuch führt verständlich und ohne technisches Vorwissen durch die Einrichtung und Nutzung der Autodarts-Steuerungsbox.

Wähle die passende Anleitung für deine Rolle:
* **[Rolle 1: Empfänger / Neuer Nutzer](#-rolle-1-empfänger--neuer-nutzer-fertige-box-erhalten)** – Du hast eine fertig konfigurierte Box erhalten und möchtest einfach nur loslegen.
* **[Rolle 2: Selbsteinrichter](#-rolle-2-selbsteinrichter-eigenen-mini-pc-von-grund-auf-einrichten)** – Du möchtest deinen eigenen Mini-PC oder Raspberry Pi komplett neu für dein Dartboard aufsetzen.
* **[Rolle 3: Vorbereiter / Schenkender](#-rolle-3-vorbereiter--schenkender-box-für-freunde-einrichten--übergeben)** – Du richtest ein Gerät für einen Freund ein und möchtest es nach dem Funktionstest sauber ohne deine privaten WLAN-Daten übergeben.

---

## 🎯 Rolle 1: Empfänger / Neuer Nutzer (Fertige Box erhalten)

Du hast eine fertig eingerichtete Autodarts-Box erhalten. Du brauchst **keinen Monitor und keine Tastatur**.

### Schritt 1: Anschließen
1. Verbinde die Kameras mit den USB-Ports des Mini-PCs.
2. Stecke das Stromkabel ein. Der Mini-PC fährt automatisch hoch.

### Schritt 2: Netzwerk auswählen

#### Möglichkeit A: Mit Netzwerkkabel (Ethernet) – am einfachsten
1. Stecke ein Netzwerkkabel von deinem Router in die Box.
2. Fertig! Öffne an deinem Smartphone, Tablet oder PC im Browser:
   👉 **`http://autodarts.local`** (oder alternativ die IP-Adresse der Box aus deinem Router).

#### Möglichkeit B: Mit WLAN (kabellos)
1. Warte nach dem Einschalten ca. **30 bis 45 Sekunden**, bis die Box hochgefahren ist.
2. Da die Box dein Heimnetzwerk noch nicht kennt, startet sie automatisch einen Einrichtungs-Hotspot.
3. Öffne an deinem Smartphone oder Laptop die **WLAN-Einstellungen** und suche nach neuen Netzwerken.
4. Verbinde dich mit:
   * **WLAN-Name (SSID):** `Autodarts-Setup`
   * **Passwort:** `autodarts123`
5. Öffne nach erfolgreicher Verbindung deinen Webbrowser und rufe auf:
   👉 **`http://autodarts.local`** (Ersatzadresse falls mDNS nicht reagiert: `http://192.168.4.1`)
6. Auf der Startseite öffnet sich automatisch das Fenster **WLAN einrichten**:
   * Wähle dein Heim-WLAN aus der Liste aus (fehlt es, tippe auf **Neu suchen**).
   * Gib dein WLAN-Passwort ein und tippe auf **Mit diesem WLAN verbinden**.
7. Die Box speichert die Zugangsdaten und verbindet sich mit deinem Heim-WLAN. Der temporäre Einrichtungs-Hotspot schaltet sich automatisch ab.
8. Verbinde dein Smartphone/Tablet wieder mit deinem normalen Heim-WLAN.

### Schritt 3: Darts spielen!
Rufe im Browser einfach künftig auf:
👉 **`http://autodarts.local`**

*Tipp: Speichere dir die Seite als Lesezeichen oder Icon auf dem Startbildschirm deines Handys oder Tablets.*

---

## 🛠️ Rolle 2: Selbsteinrichter (Eigenen Mini-PC von Grund auf einrichten)

Du hast einen Mini-PC (x86_64) oder einen Raspberry Pi 4/5 und möchtest die Headless-Steuerung selbst installieren.

### Schritt 1: Betriebssystem installieren
* **Raspberry Pi:** Mit dem *Raspberry Pi Imager* **Raspberry Pi OS (64-Bit)** auf die SD-Karte schreiben. Im Imager lassen sich gleich WLAN und SSH voreinstellen – dann brauchst du auch hier keinen Monitor.
* **Mini-PC:** Ein beliebiges aktuelles 64-Bit-Linux, z. B. **Debian 12/13**, **Ubuntu 24.04 LTS**, **Linux Mint**, **Fedora**, **Arch Linux** oder **openSUSE** (vollständige Liste im [README](../README.md#unterstützte-linux-distributionen--systemvoraussetzungen)).
* Der Rechner braucht während der Installation eine Internetverbindung (Ethernet oder WLAN).
* WLAN und Setup-Hotspot funktionieren nur, wenn **NetworkManager** das WLAN verwaltet. Bei Raspberry Pi OS, Fedora und allen Desktop-Varianten ist das automatisch so; der Installer weist dich darauf hin, falls nicht.

### Schritt 2: Autodarts Headless Control installieren

Öffne am Mini-PC ein Terminal (oder verbinde dich per SSH) und gib **diesen einen Befehl** ein:

```bash
curl -fsSL https://github.com/xXxecutor/autodarts-headless-control/releases/latest/download/install.sh | sudo bash
```

*Fehlt `curl` (manche minimalen Debian-Installationen), funktioniert dasselbe mit `wget -qO- <gleiche Adresse> | sudo bash`. Fehlt auch `sudo`, als root ausführen: `su -c "wget -qO- <gleiche Adresse> | bash"`. Git wird nicht benötigt.*

Das dauert je nach Internetverbindung einige Minuten. Der Installer richtet alles automatisch ein:
* Alle benötigten Linux-Pakete (NetworkManager, Avahi, polkit, Firewall …) über die Paketverwaltung deiner Distribution
* Den Systembenutzer `autodarts` mit Kamerazugriff, der ohne Anmeldung startet
* Die Adresse `http://autodarts.local`, die Firewall und passwortlose Rechte für WLAN, Neustart und Herunterfahren
* Ein bereits eingerichtetes WLAN wird an NetworkManager übergeben, damit WLAN-Einrichtung und Setup-Hotspot funktionieren
* Autodarts selbst (headless) – inklusive Autostart als Hintergrunddienst
* Automatische Updates für Autodarts und Headless Control (täglich, ohne dein Zutun)

Starte den Rechner anschließend einmal neu:
```bash
sudo reboot
```

> **Lieber manuell (Debian/Ubuntu/Raspberry Pi OS)?** Lade die Datei `autodarts-headless-control_<Version>_all.deb` aus den [Releases](https://github.com/xXxecutor/autodarts-headless-control/releases) herunter (z. B. auf einem anderen Rechner und per USB-Stick übertragen) und installiere sie mit `sudo apt install ./autodarts-headless-control_<Version>_all.deb`. Eine Internetverbindung am Mini-PC ist trotzdem nötig, weil dabei Systempakete und Autodarts selbst heruntergeladen werden.

> **Hinweis zur Netzwerkverwaltung:** WLAN-Einrichtung und Setup-Hotspot setzen voraus, dass `NetworkManager` das WLAN verwaltet. Bei Raspberry Pi OS, Fedora und Desktop-Varianten ist das Standard; bei Debian- und Ubuntu-Server-Installationen stellt der Installer das automatisch um (wirksam nach dem Neustart). Gibt der Installer dazu am Ende einen gelben Hinweis aus (z. B. bei WLAN mit fester IP-Adresse), funktioniert die Box per LAN trotzdem vollständig – nur WLAN-Einrichtung und Hotspot nicht.
>
> **Port 80 belegt?** Läuft auf dem Rechner schon ein Webserver, weicht die Oberfläche automatisch auf `http://autodarts.local:8080` aus; der Installer zeigt die Adresse am Ende an.

### Schritt 3: Erstinbetriebnahme & Board-Kalibrierung
1. Rufe im Browser an einem beliebigen Gerät im selben Netzwerk `http://autodarts.local` auf.
2. Klicke auf **„Board einrichten“**. Der offizielle Autodarts Board-Manager öffnet sich in einem neuen Tab.
3. Melde das Board an deinem Autodarts-Konto an, ordne die Kameras zu und kalibriere das Board.
4. Fertig! Autodarts wurde automatisch als Hintergrunddienst eingerichtet und startet bei jedem Einschalten von selbst. Gespielt wird auf **play.autodarts.com**.

*Hinweis:* Zeigt die Startseite „Board-Manager nicht erreichbar“, läuft eine Autodarts-Version vor 2.1. Dann steht dort die **Terminal-Einrichtung (Fallback)** zur Verfügung.

---

## 🎁 Rolle 3: Vorbereiter / Schenkender (Box für Freunde einrichten & übergeben)

Du möchtest einem Freund oder Vereinskollegen eine fertig aufgebaute Autodarts-Box schenken oder verkaufen. Deine eigenen privaten WLAN-Passwörter dürfen dabei keinesfalls auf dem Gerät verbleiben.

### Schritt 1: Vorbereitung & Test
1. Führe die Schritte aus **[Rolle 2: Selbsteinrichter](#-rolle-2-selbsteinrichter-eigenen-mini-pc-von-grund-auf-einrichten)** bei dir zu Hause durch.
2. Schließe die Kameras an und kalibriere das System vollständig, sodass Autodarts einsatzbereit ist.
3. Teste ein kurzes Match oder die Board-Erkennung im Browser.

### Schritt 2: Sichere Übergabe (Handover-Modus)
Bevor du das Gerät einpackst:
1. Öffne an deinem PC oder Handy die Admin-Oberfläche der Box:
   👉 **`http://autodarts.local/admin`**
2. Gehe zum Bereich **„Gerät übergeben“**.
3. Klicke auf den roten Button **„WLAN-Zugangsdaten löschen“** und bestätige mit **„Löschen“**.
4. **Was das System jetzt tut:**
   * ✅ Alle über die Weboberfläche gespeicherten WLAN-Verbindungen (`autodarts-*`) werden rückstandsfrei gelöscht.
   * 🛡️ Die Autodarts-Installation, Board-Kalibrierung, Kamera-Einstellungen und das Betriebssystem bleiben zu 100 % erhalten.
   * 🔄 Das Gerät bereitet sich darauf vor, beim nächsten Start beim Empfänger automatisch den Einrichtungs-Hotspot (`Autodarts-Setup`) zu starten, da kein bekanntes WLAN mehr hinterlegt ist.

### Schritt 3: Herunterfahren & Übergeben
1. Tippe auf der Startseite oben rechts auf das **Ein/Aus-Symbol** (Herunterfahren) und bestätige.
2. Sobald „System ist aus“ erscheint und die LEDs am Gerät erloschen sind, ziehe das Netzteil ab.
3. Gib dem Empfänger die Box zusammen mit dem Abschnitt **[Rolle 1: Empfänger / Neuer Nutzer](#-rolle-1-empfänger--neuer-nutzer-fertige-box-erhalten)** an die Hand.

---

## ❓ Häufige Fragen & Problemlösungen (FAQ)

### 1. `http://autodarts.local` lässt sich im Browser nicht öffnen
* **Android-Smartphones:** Manche ältere Android-Versionen oder bestimmte Browser (z. B. manche Chrome-Mobilversionen) unterstützen kein mDNS.
  * *Lösung:* Wenn du mit dem Hotspot verbunden bist, nutze die IP-Adresse `http://192.168.4.1`. Im Heimnetzwerk prüfe die IP-Adresse der Box in deiner Router-Übersicht (z. B. Fritz!Box unter `http://fritz.box`).
* **VLAN oder Gast-WLAN:** Befindet sich dein Handy im „Gastnetzwerk“, blockieren Router oft die Kommunikation zwischen Geräten. Verbinde beide Geräte mit dem normalen Hauptnetz.

### 2. WLAN-Passwort falsch eingegeben
* Die Box kann sich nicht mit dem Router verbinden und aktiviert nach kurzer Zeit automatisch wieder den Hotspot `Autodarts-Setup`.
* Verbinde dich einfach erneut mit dem Hotspot und gib das Passwort noch einmal ein.

### 3. Funktioniert die Box auch ohne Internet?
* **Ja!** Die Headless-Steuerung, Weboberfläche und lokale Diagnose funktionieren komplett offline im lokalen Netzwerk. (Hinweis: Autodarts selbst benötigt für Online-Multiplayer-Matches gegen andere Spieler Internet; lokale Trainingsspiele funktionieren).

### 4. Muss ich mich nach dem Einschalten am Mini-PC einloggen oder ein Passwort eingeben?
* **Nein, absolut nicht.** Das System ist vollständig für den sogenannten „Headless“-Betrieb (ohne Bildschirm und Tastatur) ausgelegt.
* Alle Systemdienste (die Weboberfläche, der WLAN-Manager und Autodarts) starten beim Hochfahren des Betriebssystems vollautomatisch im Hintergrund – noch bevor überhaupt ein Benutzerlogin stattfinden würde.
* Auch bei Aktionen in der Weboberfläche (wie Neustart, Herunterfahren oder WLAN-Verbindung) ist durch die vorkonfigurierten Polkit-Rechte keine Passworteingabe am Gerät erforderlich.

### 5. Muss ich Updates selbst installieren?
* **Nein.** Autodarts und Autodarts Headless Control aktualisieren sich einmal täglich automatisch, sobald die Box mit dem Internet verbunden ist. Die installierte Version siehst du unter `http://autodarts.local/admin` im Bereich **System-Informationen**.

### 6. Ich habe zwei Boxen im selben Netzwerk – wie erreiche ich die zweite?
* Beide melden sich als `autodarts.local`; die zweite Box weicht automatisch auf `autodarts-2.local` aus. Alternativ hilft die IP-Adresse aus der Router-Übersicht.
