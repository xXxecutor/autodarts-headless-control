import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


class TestFirewallSyncScript(unittest.TestCase):
    """Testet installer/autodarts-firewall-sync und installer/90-autodarts-firewall mit Mocks."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.bin_dir = Path(self.temp_dir.name) / "bin"
        self.state_dir = Path(self.temp_dir.name) / "state"
        self.bin_dir.mkdir(parents=True)
        self.state_dir.mkdir(parents=True)

        self.repo_root = Path(__file__).resolve().parent.parent
        self.sync_script = self.repo_root / "installer" / "autodarts-firewall-sync"
        self.dispatcher_script = self.repo_root / "installer" / "90-autodarts-firewall"

        self.mock_log = Path(self.temp_dir.name) / "mock_calls.log"

    def tearDown(self):
        self.temp_dir.cleanup()

    def _create_mock(self, name: str, script_content: str):
        path = self.bin_dir / name
        with open(path, "w") as f:
            f.write(f"#!/usr/bin/env bash\n{script_content}\n")
        path.chmod(0o755)

    def test_syntax_of_firewall_scripts(self):
        """Prüft, ob beide Skripte syntaktisch korrektes Bash sind."""
        for script in (self.sync_script, self.dispatcher_script):
            res = subprocess.run(
                ["bash", "-n", str(script)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(res.returncode, 0, f"Syntaxfehler in {script}: {res.stderr}")

    def test_dispatcher_filters_events(self):
        """Prüft, ob 90-autodarts-firewall nur bei relevanten Events das Sync-Skript aufruft."""
        # Mock für /usr/local/sbin/autodarts-firewall-sync
        mock_sync = self.bin_dir / "autodarts-firewall-sync"
        with open(mock_sync, "w") as f:
            f.write("#!/usr/bin/env bash\necho SYNC_TRIGGERED >> " + str(self.mock_log) + "\n")
        mock_sync.chmod(0o755)

        # Temp-Kopie des Dispatchers, die auf den Mock-Pfad verweist
        custom_dispatcher = Path(self.temp_dir.name) / "test-dispatcher"
        content = self.dispatcher_script.read_text().replace(
            "/usr/local/sbin/autodarts-firewall-sync", str(mock_sync)
        )
        custom_dispatcher.write_text(content)
        custom_dispatcher.chmod(0o755)

        # 1. Nicht beachtetes Event (z. B. 'hostname')
        subprocess.run([str(custom_dispatcher), "none", "hostname"], check=True)
        if self.mock_log.exists():
            self.assertEqual(self.mock_log.read_text().strip(), "")

        # 2. Relevantes Event: 'up'
        subprocess.run([str(custom_dispatcher), "wlan0", "up"], check=True)
        self.assertTrue(self.mock_log.exists())
        self.assertIn("SYNC_TRIGGERED", self.mock_log.read_text())

        # 3. Relevantes Event: 'connectivity-change'
        self.mock_log.unlink()
        subprocess.run([str(custom_dispatcher), "", "connectivity-change"], check=True)
        self.assertIn("SYNC_TRIGGERED", self.mock_log.read_text())

    def _prepare_testable_sync_script(self):
        """Erstellt eine Kopie des Sync-Skripts mit umgeleiteten State-/Lock-/Avahi-Pfaden und ohne EUID-Prüfung."""
        dummy_avahi = Path(self.temp_dir.name) / "default_avahi.conf"
        if not dummy_avahi.exists():
            dummy_avahi.write_text("[server]\n#allow-interfaces=\n")
        dummy_orig = Path(self.temp_dir.name) / "default_avahi.conf.orig"

        raw = self.sync_script.read_text()
        # Pfade und EUID-Check für isolierte Testumgebung patchen
        patched = raw.replace(
            'STATE_DIR="/var/lib/autodarts-headless-control-firewall"',
            f'STATE_DIR="{self.state_dir}"',
        ).replace(
            'LOCK_FILE="/run/autodarts-firewall-sync.lock"',
            f'LOCK_FILE="{self.temp_dir.name}/sync.lock"',
        ).replace(
            'conf="/etc/avahi/avahi-daemon.conf"',
            f'conf="{dummy_avahi}"',
        ).replace(
            'orig="/etc/avahi/avahi-daemon.conf.orig"',
            f'orig="{dummy_orig}"',
        ).replace(
            '[[ $EUID -eq 0 ]] || exit 1',
            '# [[ $EUID -eq 0 ]] || exit 1',
        )
        script_path = Path(self.temp_dir.name) / "testable-firewall-sync"
        script_path.write_text(patched)
        script_path.chmod(0o755)
        return script_path

    def test_hotspot_detection_and_rules(self):
        """Prüft, dass bei aktivem Hotspot (192.168.4.1/24) Hotspot-Regeln gesetzt werden."""
        script_path = self._prepare_testable_sync_script()
        ufw_calls = Path(self.temp_dir.name) / "ufw_calls.log"

        # Mock nmcli: meldet wlan0 mit autodarts-hotspot-setup
        self._create_mock("nmcli", """
if [[ "$*" == *"-t -f DEVICE,TYPE,STATE device status"* ]]; then
    echo "wlan0:wifi:connected"
elif [[ "$*" == *"-g GENERAL.CONNECTION device show wlan0"* ]]; then
    echo "autodarts-hotspot-setup"
elif [[ "$*" == *"-g GENERAL.TYPE device show"* ]]; then
    echo "wifi"
fi
""")
        # Mock ip: liefert 192.168.4.1/24 für wlan0
        self._create_mock("ip", """
if [[ "$*" == *"-o -4 addr show dev wlan0 scope global"* ]]; then
    echo "wlan0 inet 192.168.4.1/24 brd 192.168.4.255 scope global wlan0"
elif [[ "$*" == *"-4 route show default"* ]]; then
    echo "default via 192.168.4.1 dev wlan0"
fi
""")
        # Mock ufw: loggt Aufrufe und simuliert leeren Status
        self._create_mock("ufw", f"""
echo "UFW: $*" >> "{ufw_calls}"
if [[ "$*" == *"status numbered"* ]]; then
    echo "[ 1] 22/tcp ALLOW IN Anywhere # SSH"
fi
""")
        self._create_mock("logger", 'echo "LOG: $*" >> "' + str(self.mock_log) + '"')

        env = os.environ.copy()
        env["PATH"] = f"{self.bin_dir}:{env['PATH']}"

        res = subprocess.run([str(script_path)], env=env, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"Fehler beim Ausführen: {res.stderr}")

        # Prüfen, ob State-File geschrieben wurde
        state_file = self.state_dir / "active-state"
        self.assertTrue(state_file.exists())
        self.assertEqual(state_file.read_text().strip(), "hotspot|wlan0|192.168.4.0/24|v3|80|8092")

        # Prüfen, ob UFW Hotspot-Regeln aufgerufen wurden
        ufw_log = ufw_calls.read_text()
        self.assertIn("Autodarts HTTP Hotspot", ufw_log)
        self.assertIn("Autodarts WebSocket Hotspot", ufw_log)
        self.assertIn("Autodarts Board-Manager Hotspot", ufw_log)
        self.assertIn("port 3180 proto tcp", ufw_log)
        self.assertIn("Autodarts mDNS Hotspot", ufw_log)
        self.assertIn("Autodarts DNS Hotspot", ufw_log)
        self.assertIn("Autodarts DHCP Hotspot", ufw_log)
        self.assertIn("from 192.168.4.0/24", ufw_log)
        self.assertNotIn("delete 1", ufw_log)  # SSH-Regel darf nicht gelöscht werden

    def test_lan_detection_and_idempotency(self):
        """Prüft, dass bei regulärem LAN LAN-Regeln gesetzt werden und wiederholter Aufruf no-op ist."""
        script_path = self._prepare_testable_sync_script()
        ufw_calls = Path(self.temp_dir.name) / "ufw_calls.log"

        # Mock nmcli: normales LAN (kein Hotspot)
        self._create_mock("nmcli", """
if [[ "$*" == *"-t -f DEVICE,TYPE,STATE device status"* ]]; then
    echo "wlan0:wifi:connected"
elif [[ "$*" == *"-g GENERAL.CONNECTION device show wlan0"* ]]; then
    echo "MyHomeWifi"
elif [[ "$*" == *"-g GENERAL.TYPE device show wlan0"* ]]; then
    echo "wifi"
fi
""")
        # Mock ip: liefert 192.168.2.129/24 (im echten Format von ip -o -4 addr)
        self._create_mock("ip", """
if [[ "$*" == *"-o -4 addr show dev wlan0 scope global"* ]]; then
    echo "2: wlan0    inet 192.168.2.129/24 brd 192.168.2.255 scope global wlan0"
elif [[ "$*" == *"-4 route show default"* ]]; then
    echo "default via 192.168.2.1 dev wlan0 proto dhcp src 192.168.2.129 metric 600"
fi
""")
        self._create_mock("ufw", f"""
echo "UFW: $*" >> "{ufw_calls}"
if [[ "$*" == *"status numbered"* ]]; then
    echo "[ 1] 22/tcp ALLOW IN Anywhere # SSH"
fi
""")
        self._create_mock("logger", 'echo "LOG: $*" >> "' + str(self.mock_log) + '"')

        env = os.environ.copy()
        env["PATH"] = f"{self.bin_dir}:{env['PATH']}"

        # 1. Erster Lauf: Erzeugt LAN-Regeln
        res = subprocess.run([str(script_path)], env=env, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"Fehler: {res.stderr}")

        state_file = self.state_dir / "active-state"
        self.assertTrue(state_file.exists())
        self.assertEqual(state_file.read_text().strip(), "lan|wlan0|192.168.2.0/24|v3|80|8092")

        ufw_log = ufw_calls.read_text()
        self.assertIn("Autodarts HTTP LAN", ufw_log)
        self.assertIn("from 192.168.2.0/24", ufw_log)

        # 2. Zweiter Lauf: Soll Idempotent sein (keine UFW-Aufrufe mehr)
        ufw_calls.unlink()
        res2 = subprocess.run([str(script_path)], env=env, capture_output=True, text=True)
        self.assertEqual(res2.returncode, 0)
        self.assertFalse(ufw_calls.exists(), "Bei identischem Zustand dürfen keine UFW-Befehle laufen")

    def test_avahi_interface_sync_behavior(self):
        """Prüft, dass Avahi-Konfiguration gesichert, gezielt aktualisiert und nicht blind überschrieben wird."""
        script_path = self._prepare_testable_sync_script()
        avahi_conf = Path(self.temp_dir.name) / "default_avahi.conf"
        avahi_orig = Path(self.temp_dir.name) / "default_avahi.conf.orig"

        sample_conf = """[server]
#host-name=foo
use-ipv4=yes
use-ipv6=yes
#allow-interfaces=eth0
ratelimit-interval-usec=1000000

[publish]
publish-workstation=yes
"""
        avahi_conf.write_text(sample_conf)
        if avahi_orig.exists():
            avahi_orig.unlink()

        # Mock nmcli und ip für wlan0
        self._create_mock("nmcli", """
if [[ "$*" == *"-t -f DEVICE,TYPE,STATE device status"* ]]; then
    echo "wlan0:wifi:connected"
elif [[ "$*" == *"-g GENERAL.CONNECTION device show wlan0"* ]]; then
    echo "HomeLAN"
elif [[ "$*" == *"-g GENERAL.TYPE device show wlan0"* ]]; then
    echo "wifi"
fi
""")
        self._create_mock("ip", """
if [[ "$*" == *"-o -4 addr show dev wlan0 scope global"* ]]; then
    echo "2: wlan0    inet 192.168.2.129/24 brd 192.168.2.255 scope global wlan0"
elif [[ "$*" == *"-4 route show default"* ]]; then
    echo "default via 192.168.2.1 dev wlan0"
fi
""")
        self._create_mock("ufw", 'echo "UFW" >> /dev/null')
        self._create_mock("logger", 'echo "LOG: $*" >> "' + str(self.mock_log) + '"')

        env = os.environ.copy()
        env["PATH"] = f"{self.bin_dir}:{env['PATH']}"

        # 1. Ausführen
        res = subprocess.run([str(script_path)], env=env, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"Fehler: {res.stderr}")

        # Backup muss existieren und exakt sample_conf entsprechen
        self.assertTrue(avahi_orig.exists(), "Originalkonfiguration muss gesichert werden")
        self.assertEqual(avahi_orig.read_text(), sample_conf)

        # Neue Konfiguration muss allow-interfaces=wlan0 enthalten
        updated = avahi_conf.read_text()
        self.assertIn("allow-interfaces=wlan0", updated)
        # Andere Konfigurationen müssen erhalten geblieben sein
        self.assertIn("publish-workstation=yes", updated)
        self.assertIn("use-ipv4=yes", updated)
        self.assertIn("ratelimit-interval-usec=1000000", updated)


if __name__ == "__main__":
    unittest.main()
