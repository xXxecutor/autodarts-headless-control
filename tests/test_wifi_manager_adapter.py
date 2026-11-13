import unittest
from unittest.mock import MagicMock, patch

from app.adapters.wifi_manager import (
    ConnectionResult,
    HotspotConfig,
    NetworkManagerBackend,
    WifiNetwork,
    create_wifi_manager,
)


class TestNetworkManagerBackend(unittest.TestCase):
    def setUp(self):
        # Unabhängig davon, ob nmcli auf dem Testrechner installiert ist.
        with patch("shutil.which", return_value="/usr/bin/nmcli"):
            self.backend = NetworkManagerBackend(sudo_prefix=["sudo", "-n"])

    @patch("shutil.which", return_value="/usr/bin/nmcli")
    def test_is_available_when_nmcli_exists(self, mock_which):
        backend = NetworkManagerBackend()
        self.assertTrue(backend.is_available())
        self.assertEqual(backend.backend_name, "NetworkManager")

    @patch("shutil.which", return_value=None)
    def test_is_available_when_nmcli_missing(self, mock_which):
        backend = NetworkManagerBackend()
        self.assertFalse(backend.is_available())

    @patch("app.adapters.wifi_manager.networkmanager.subprocess.run")
    def test_scan_networks_parses_output(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=(
                "TestSSID:75:WPA2:2412:*\n"
                "OtherNet:50:WPA3:5180:\n"
                "OpenNet:30::2437:\n"
            ),
            stderr="",
        )

        networks = self.backend.scan_networks("wlan0")

        self.assertEqual(len(networks), 3)
        self.assertEqual(networks[0].ssid, "TestSSID")
        self.assertEqual(networks[0].signal, 75)
        self.assertEqual(networks[0].security, "WPA2")
        self.assertEqual(networks[0].frequency, 2412)
        self.assertTrue(networks[0].in_use)

        self.assertEqual(networks[1].ssid, "OtherNet")
        self.assertFalse(networks[1].in_use)

        self.assertEqual(networks[2].security, "open")

    @patch("app.adapters.wifi_manager.networkmanager.subprocess.run")
    def test_scan_networks_handles_empty_output(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        networks = self.backend.scan_networks("wlan0")
        self.assertEqual(networks, [])

    @patch("app.adapters.wifi_manager.networkmanager.subprocess.run")
    def test_connect_creates_and_activates_profile(self, mock_run):
        # Sequence: delete old -> create -> up
        mock_run.side_effect = [
            MagicMock(returncode=0),  # delete (may fail if not exists)
            MagicMock(returncode=0),  # connection add
            MagicMock(returncode=0),  # connection up
        ]

        result = self.backend.connect("wlan0", "MySSID", "mypassword")

        self.assertTrue(result.success)
        self.assertEqual(result.connection_name, "autodarts-MySSID")
        self.assertEqual(mock_run.call_count, 3)

        # Verify create call includes security args
        create_call = mock_run.call_args_list[1]
        args = create_call[0][0]
        self.assertIn("wifi-sec.key-mgmt", args)
        self.assertIn("wpa-psk", args)
        self.assertIn("wifi-sec.psk", args)
        self.assertIn("mypassword", args)

    @patch("app.adapters.wifi_manager.networkmanager.subprocess.run")
    def test_connect_open_network_no_password(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0),
            MagicMock(returncode=0),
            MagicMock(returncode=0),
        ]

        result = self.backend.connect("wlan0", "OpenNet", "")

        self.assertTrue(result.success)
        create_call = mock_run.call_args_list[1]
        args = create_call[0][0]
        self.assertIn("wifi-sec.key-mgmt", args)
        self.assertIn("none", args)
        self.assertNotIn("wifi-sec.psk", args)

    @patch("app.adapters.wifi_manager.networkmanager.subprocess.run")
    def test_connect_failure_on_create(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0),
            MagicMock(returncode=1, stderr="Error: connection already exists"),
        ]

        result = self.backend.connect("wlan0", "MySSID", "pass")
        self.assertFalse(result.success)
        self.assertIn("Failed to create connection", result.message)

    @patch("app.adapters.wifi_manager.networkmanager.subprocess.run")
    def test_connect_failure_on_activate_cleans_up(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0),  # delete
            MagicMock(returncode=0),  # create
            MagicMock(returncode=1, stderr="Activation failed"),  # up fails
            MagicMock(returncode=0),  # cleanup delete
        ]

        result = self.backend.connect("wlan0", "MySSID", "pass")
        self.assertFalse(result.success)
        self.assertIn("Failed to activate", result.message)
        self.assertEqual(mock_run.call_count, 4)

    @patch("threading.Thread")
    @patch("app.adapters.wifi_manager.networkmanager.subprocess.run")
    def test_connect_deferred_activation(self, mock_run, mock_thread_cls):
        mock_run.side_effect = [
            MagicMock(returncode=0),  # delete old
            MagicMock(returncode=0),  # connection add
        ]
        mock_thread = MagicMock()
        mock_thread_cls.return_value = mock_thread

        result = self.backend.connect("wlan0", "DeferredNet", "secret", deferred_activation=True)

        self.assertTrue(result.success)
        self.assertIn("WLAN-Profil für 'DeferredNet' gespeichert", result.message)
        self.assertEqual(result.connection_name, "autodarts-DeferredNet")
        mock_thread_cls.assert_called_once()
        mock_thread.start.assert_called_once()

    @patch("app.adapters.wifi_manager.networkmanager.subprocess.run")
    def test_start_hotspot_creates_ap_connection(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0),  # delete existing
            MagicMock(returncode=0),  # create
            MagicMock(returncode=0),  # up
        ]

        config = HotspotConfig(ssid="Autodarts-Setup", password="autodarts123")
        result = self.backend.start_hotspot("wlan0", config)

        self.assertTrue(result.success)
        self.assertTrue(result.connection_name.startswith("autodarts-hotspot-"))

        create_call = mock_run.call_args_list[1]
        args = create_call[0][0]
        self.assertIn("wifi.mode", args)
        self.assertIn("ap", args)
        self.assertIn("ipv4.method", args)
        self.assertIn("shared", args)
        self.assertIn("wifi-sec.psk", args)
        self.assertIn("autodarts123", args)

    @patch("app.adapters.wifi_manager.networkmanager.subprocess.run")
    def test_stop_hotspot_down_and_delete(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0),  # down
            MagicMock(returncode=0),  # delete
        ]

        result = self.backend.stop_hotspot("wlan0", "autodarts-hotspot-test")

        self.assertTrue(result.success)
        self.assertEqual(mock_run.call_count, 2)

    @patch("threading.Thread")
    @patch("app.adapters.wifi_manager.networkmanager.subprocess.run")
    def test_start_hotspot_deferred(self, mock_run, mock_thread_cls):
        mock_run.side_effect = [
            MagicMock(returncode=0),  # delete existing
            MagicMock(returncode=0),  # create
        ]
        mock_thread = MagicMock()
        mock_thread_cls.return_value = mock_thread

        config = HotspotConfig(ssid="Autodarts-Setup", password="autodarts123")
        result = self.backend.start_hotspot("wlan0", config, deferred=True)

        self.assertTrue(result.success)
        self.assertIn("Hotspot 'Autodarts-Setup' wird gestartet", result.message)
        mock_thread_cls.assert_called_once()
        mock_thread.start.assert_called_once()

    @patch("threading.Thread")
    def test_stop_hotspot_deferred(self, mock_thread_cls):
        mock_thread = MagicMock()
        mock_thread_cls.return_value = mock_thread

        result = self.backend.stop_hotspot("wlan0", "autodarts-hotspot-test", deferred=True)

        self.assertTrue(result.success)
        self.assertIn("Hotspot wird beendet", result.message)
        mock_thread_cls.assert_called_once()
        mock_thread.start.assert_called_once()

    @patch("app.adapters.wifi_manager.networkmanager.subprocess.run")
    def test_get_active_connections(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="autodarts-MySSID:wifi:wlan0:activated\nWired connection 1:ethernet:eth0:activated\n",
            stderr="",
        )

        connections = self.backend.get_active_connections()

        self.assertEqual(len(connections), 2)
        self.assertEqual(connections[0]["name"], "autodarts-MySSID")
        self.assertEqual(connections[0]["type"], "wifi")
        self.assertEqual(connections[0]["device"], "wlan0")
        self.assertEqual(connections[0]["state"], "activated")

    @patch("app.adapters.wifi_manager.networkmanager.subprocess.run")
    def test_get_saved_connections(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="autodarts-MySSID:802-11-wireless:wlan0\nautodarts-hotspot-test:802-11-wireless:\nnetplan-eth0:802-3-ethernet:\n",
            stderr="",
        )

        connections = self.backend.get_saved_connections()

        self.assertEqual(len(connections), 3)
        self.assertEqual(connections[0]["name"], "autodarts-MySSID")
        self.assertEqual(connections[0]["device"], "wlan0")
        self.assertEqual(connections[1]["name"], "autodarts-hotspot-test")
        self.assertEqual(connections[1]["device"], "")
        self.assertEqual(connections[2]["name"], "netplan-eth0")

    @patch("app.adapters.wifi_manager.networkmanager.subprocess.run")
    def test_delete_connection_only_autodarts_prefixed(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)

        # Should succeed for autodarts connections
        result = self.backend.delete_connection("autodarts-MySSID")
        self.assertTrue(result.success)

        result = self.backend.delete_connection("autodarts-hotspot-test")
        self.assertTrue(result.success)

        # Should refuse non-autodarts connections
        result = self.backend.delete_connection("Wired connection 1")
        self.assertFalse(result.success)
        self.assertIn("Refusing to delete", result.message)


class TestWifiManagerFactory(unittest.TestCase):
    @patch("app.adapters.wifi_manager.factory.NetworkManagerBackend")
    def test_creates_nm_backend(self, mock_nm_class):
        mock_nm = MagicMock()
        mock_nm_class.return_value = mock_nm

        backend = create_wifi_manager()
        self.assertIs(backend, mock_nm)
        mock_nm_class.assert_called_once_with(None)

    @patch("app.adapters.wifi_manager.factory.NetworkManagerBackend")
    def test_creates_nm_backend_with_sudo_prefix(self, mock_nm_class):
        mock_nm = MagicMock()
        mock_nm_class.return_value = mock_nm

        backend = create_wifi_manager(sudo_prefix=["sudo", "-n"])
        self.assertIs(backend, mock_nm)
        mock_nm_class.assert_called_once_with(["sudo", "-n"])


if __name__ == "__main__":
    unittest.main()