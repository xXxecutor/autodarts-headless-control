import importlib.util
import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "installer" / "migrate-network.py"


def load_module():
    spec = importlib.util.spec_from_file_location("migrate_network", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestMigrateNetwork(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.mod = load_module()
        self.mod.INTERFACES = str(self.root / "interfaces")
        self.mod.NM_DIR = str(self.root / "system-connections")
        self.mod.NETPLAN_DIR = str(self.root / "netplan")
        self.mod.NETPLAN_FILE = str(self.root / "netplan" / "99-autodarts-networkmanager.yaml")

    def tearDown(self):
        self.tmp.cleanup()

    def run_ifupdown(self, content, wifi=("wlan0",)):
        Path(self.mod.INTERFACES).write_text(content, encoding="utf-8")
        out = io.StringIO()
        with redirect_stdout(out):
            self.mod.migrate_ifupdown(set(wifi))
        return out.getvalue()

    def profiles(self):
        d = Path(self.mod.NM_DIR)
        return sorted(d.glob("*.nmconnection")) if d.exists() else []

    def test_wpa_ssid_is_migrated_and_ethernet_kept(self):
        self.run_ifupdown(
            "auto lo eth0 wlan0\n"
            "iface lo inet loopback\n"
            "iface eth0 inet dhcp\n"
            "allow-hotplug wlan0\n"
            "iface wlan0 inet dhcp\n"
            '    wpa-ssid "Bob\'s WLAN"\n'
            '    wpa-psk "geheim123"\n'
        )
        profiles = self.profiles()
        self.assertEqual(len(profiles), 1)
        text = profiles[0].read_text(encoding="utf-8")
        self.assertIn("ssid=Bob's WLAN", text)
        self.assertIn("psk=geheim123", text)
        self.assertIn("id=autodarts-Bob's WLAN", text)
        self.assertEqual(os.stat(profiles[0]).st_mode & 0o777 if os.name != "nt" else 0o600, 0o600)

        result = Path(self.mod.INTERFACES).read_text(encoding="utf-8")
        self.assertIn("auto lo eth0\n", result)            # Ethernet bleibt aktiv
        self.assertIn("iface eth0 inet dhcp", result)
        self.assertIn("# [autodarts: moved to NetworkManager] iface wlan0", result)
        self.assertIn("# [autodarts: moved to NetworkManager]     wpa-psk", result)
        self.assertTrue(Path(self.mod.INTERFACES + ".autodarts-bak").exists())

    def test_wpa_conf_file_is_read(self):
        conf = self.root / "wpa.conf"
        conf.write_text('network={\n    ssid="HomeNet"\n    psk="pw12345678"\n}\n')
        self.run_ifupdown(f"iface wlan0 inet dhcp\n    wpa-conf {conf}\n")
        text = self.profiles()[0].read_text(encoding="utf-8")
        self.assertIn("ssid=HomeNet", text)
        self.assertIn("psk=pw12345678", text)

    def test_static_ip_is_left_alone(self):
        original = "iface wlan0 inet static\n    address 10.0.0.5/24\n    wpa-ssid X\n    wpa-psk Y12345678\n"
        output = self.run_ifupdown(original)
        self.assertEqual(self.profiles(), [])
        self.assertEqual(Path(self.mod.INTERFACES).read_text(encoding="utf-8"), original)
        self.assertIn("feste IP-Adresse", output)

    def test_nothing_to_do_without_wifi_stanza(self):
        original = "auto eth0\niface eth0 inet dhcp\n"
        self.run_ifupdown(original)
        self.assertEqual(Path(self.mod.INTERFACES).read_text(encoding="utf-8"), original)
        self.assertFalse(Path(self.mod.INTERFACES + ".autodarts-bak").exists())

    def test_netplan_with_networkd_wifi_switches_renderer(self):
        netplan = Path(self.mod.NETPLAN_DIR)
        netplan.mkdir()
        (netplan / "50-cloud-init.yaml").write_text(
            "network:\n  version: 2\n  wifis:\n    wlan0:\n      dhcp4: true\n      access-points:\n        Home:\n          password: x\n"
        )
        self.assertTrue(self.mod.migrate_netplan())
        self.assertIn("renderer: NetworkManager", Path(self.mod.NETPLAN_FILE).read_text(encoding="utf-8"))
        # zweiter Lauf: nichts mehr zu tun
        self.assertFalse(self.mod.migrate_netplan())

    def test_netplan_ethernet_only_is_untouched(self):
        netplan = Path(self.mod.NETPLAN_DIR)
        netplan.mkdir()
        (netplan / "50-cloud-init.yaml").write_text("network:\n  version: 2\n  ethernets:\n    eth0:\n      dhcp4: true\n")
        self.assertFalse(self.mod.migrate_netplan())
        self.assertFalse(Path(self.mod.NETPLAN_FILE).exists())


if __name__ == "__main__":
    unittest.main()
