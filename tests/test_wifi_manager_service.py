import unittest
from unittest.mock import ANY, MagicMock, patch

from app.services.network_policy import NetworkDecision
from app.services.wifi_manager import WifiManagerService


class TestWifiManagerService(unittest.TestCase):
    def setUp(self):
        # Create service with mocked dependencies using patch
        self.patcher_adapter = patch("app.services.wifi_manager.create_wifi_adapter")
        self.patcher_manager = patch("app.services.wifi_manager.create_wifi_manager")

        self.mock_create_adapter = self.patcher_adapter.start()
        self.mock_create_manager = self.patcher_manager.start()

        # Mock the wifi adapter (detection)
        self.mock_adapter = MagicMock()
        self.mock_adapter.detect.return_value = {
            "supported_platform": True,
            "tools": {"nmcli": "/usr/bin/nmcli"},
            "network_manager": "NetworkManager",
            "wireless": {"interfaces": ["wlan0"], "wireless_visible": True},
            "access_point_support": "supported",
            "network_status": {
                "available": True,
                "interfaces": [
                    {"name": "eth0", "state": "DOWN", "addresses": []},
                    {"name": "wlan0", "state": "DOWN", "addresses": []},
                ],
                "connected": False,
            },
        }
        self.mock_create_adapter.return_value = self.mock_adapter

        # Mock the wifi manager (write operations)
        self.mock_manager = MagicMock()
        self.mock_manager.backend_name = "NetworkManager"
        self.mock_manager.is_available.return_value = True
        self.mock_manager.get_active_connections.return_value = []
        self.mock_manager.get_saved_connections.return_value = []
        self.mock_manager.scan_networks.return_value = []
        self.mock_create_manager.return_value = self.mock_manager

        self.service = WifiManagerService()

    def tearDown(self):
        self.patcher_adapter.stop()
        self.patcher_manager.stop()

    def _get_mock_manager(self):
        """Helper to get the mock manager that was created."""
        return self.mock_manager

    def test_refresh_detection_calls_adapter(self):
        result = self.service.refresh_detection()
        self.mock_adapter.detect.assert_called_once()
        self.assertEqual(result, self.mock_adapter.detect.return_value)

    def test_get_network_state_combines_detection_and_manager(self):
        self.mock_manager.get_active_connections.return_value = [
            {"name": "autodarts-MyWiFi", "type": "wifi", "device": "wlan0", "state": "activated"}
        ]
        from app.adapters.wifi_manager import WifiNetwork
        self.mock_manager.scan_networks.return_value = [
            WifiNetwork(ssid="TestNet", signal=80, security="WPA2", frequency=2412, in_use=False)
        ]

        state = self.service.get_network_state()

        self.assertEqual(state.decision, NetworkDecision.START_HOTSPOT)  # No active connection
        self.assertEqual(len(state.active_connections), 1)
        self.assertEqual(len(state.available_networks), 1)
        self.assertFalse(state.hotspot_active)  # Not a hotspot connection

    def test_get_network_state_detects_hotspot(self):
        self.mock_manager.get_active_connections.return_value = [
            {"name": "autodarts-hotspot-Setup", "type": "wifi", "device": "wlan0", "state": "activated"}
        ]

        state = self.service.get_network_state()
        self.assertTrue(state.hotspot_active)

    @patch("app.services.wifi_manager.decide_network_action")
    def test_execute_policy_keep_ethernet(self, mock_decide):
        mock_decide.return_value = NetworkDecision.KEEP_ETHERNET

        result = self.service.execute_policy()

        self.assertTrue(result.success)
        self.assertIn("Ethernet active", result.message)

    @patch("app.services.wifi_manager.decide_network_action")
    def test_execute_policy_connect_wifi(self, mock_decide):
        mock_decide.return_value = NetworkDecision.CONNECT_WIFI

        result = self.service.execute_policy()

        self.assertTrue(result.success)
        self.assertIn("auto-connect", result.message)

    @patch("app.services.wifi_manager.decide_network_action")
    def test_execute_policy_start_hotspot(self, mock_decide):
        mock_decide.return_value = NetworkDecision.START_HOTSPOT
        self.mock_manager.start_hotspot.return_value = MagicMock(
            success=True, message="Hotspot started", connection_name="autodarts-hotspot-Setup"
        )

        result = self.service.execute_policy()

        self.assertTrue(result.success)
        self.mock_manager.start_hotspot.assert_called_once()

    @patch("app.services.wifi_manager.decide_network_action")
    def test_execute_policy_error_no_network(self, mock_decide):
        mock_decide.return_value = NetworkDecision.ERROR_NO_NETWORK

        result = self.service.execute_policy()

        self.assertFalse(result.success)
        self.assertIn("hotspot not supported", result.message)

    def test_connect_to_wifi_delegates_to_manager(self):
        self.mock_manager.connect.return_value = MagicMock(
            success=True, message="Connected", connection_name="autodarts-TestNet"
        )

        result = self.service.connect_to_wifi("TestNet", "password")

        self.assertTrue(result.success)
        self.mock_manager.connect.assert_called_once_with("wlan0", "TestNet", "password")

    def test_connect_to_wifi_defers_activation_when_hotspot_active(self):
        self.mock_manager.get_active_connections.return_value = [
            {"name": "autodarts-hotspot-Setup", "type": "wifi", "device": "wlan0", "state": "activated"}
        ]
        self.mock_manager.connect.return_value = MagicMock(
            success=True, message="Profile saved", connection_name="autodarts-HomeNet"
        )

        result = self.service.connect_to_wifi("HomeNet", "secret")

        self.assertTrue(result.success)
        self.mock_manager.connect.assert_called_once_with(
            "wlan0", "HomeNet", "secret", deferred_activation=True,
            on_result=ANY, recovery_hotspot=ANY,
        )

    def test_connect_to_wifi_no_interface(self):
        self.mock_adapter.detect.return_value["wireless"]["interfaces"] = []

        result = self.service.connect_to_wifi("TestNet", "password")

        self.assertFalse(result.success)
        self.assertIn("No wireless interface", result.message)

    def test_start_hotspot_manual(self):
        self.mock_manager.start_hotspot.return_value = MagicMock(
            success=True, message="Hotspot started", connection_name="autodarts-hotspot-Custom"
        )

        from app.adapters.wifi_manager import HotspotConfig
        config = HotspotConfig(ssid="CustomAP", password="custompass")

        result = self.service.start_hotspot_manual(config)

        self.assertTrue(result.success)
        self.mock_manager.start_hotspot.assert_called_once()

    def test_stop_hotspot_delegates(self):
        self.mock_manager.stop_hotspot.return_value = MagicMock(success=True, message="Stopped")

        result = self.service.stop_hotspot("autodarts-hotspot-Setup", "wlan0")

        self.assertTrue(result.success)
        self.mock_manager.stop_hotspot.assert_called_once_with("wlan0", "autodarts-hotspot-Setup")

    def test_prepare_handover_deletes_autodarts_connections(self):
        self.mock_manager.get_saved_connections.return_value = [
            {"name": "autodarts-HomeWiFi", "type": "wifi", "device": "wlan0"},
            {"name": "autodarts-hotspot-Setup", "type": "wifi", "device": ""},
            {"name": "Wired connection 1", "type": "ethernet", "device": "eth0"},
        ]
        self.mock_manager.delete_connection.side_effect = [
            MagicMock(success=True, message="Deleted"),
            MagicMock(success=True, message="Deleted"),
        ]

        result = self.service.prepare_handover()

        self.assertTrue(result.success)
        self.assertEqual(self.mock_manager.delete_connection.call_count, 2)
        # Verify only autodarts connections were deleted
        calls = self.mock_manager.delete_connection.call_args_list
        self.assertEqual(calls[0][0][0], "autodarts-HomeWiFi")
        self.assertEqual(calls[1][0][0], "autodarts-hotspot-Setup")

    def test_prepare_handover_deletes_saved_inactive_connections(self):
        # Active connection is only ethernet, but saved connection contains autodarts wifi
        self.mock_manager.get_active_connections.return_value = [
            {"name": "netplan-eth0", "type": "ethernet", "device": "eth0", "state": "activated"}
        ]
        self.mock_manager.get_saved_connections.return_value = [
            {"name": "autodarts-OldWiFi", "type": "wifi", "device": ""},
            {"name": "netplan-eth0", "type": "ethernet", "device": "eth0"},
        ]
        self.mock_manager.delete_connection.return_value = MagicMock(success=True, message="Deleted")

        result = self.service.prepare_handover()

        self.assertTrue(result.success)
        self.mock_manager.delete_connection.assert_called_once_with("autodarts-OldWiFi")

    def test_prepare_handover_deletes_wifi_from_pi_imager(self):
        # Raspberry Pi Imager: WLAN als netplan-Profil, LAN-Profil muss bleiben.
        self.mock_manager.get_saved_connections.return_value = [
            {"name": "netplan-wlan0-Orange Citadel", "type": "802-11-wireless", "device": "wlan0"},
            {"name": "netplan-eth0", "type": "802-3-ethernet", "device": ""},
            {"name": "wg0", "type": "wireguard", "device": "wg0"},
        ]
        self.mock_manager.get_active_connections.return_value = []
        self.mock_manager.delete_connection.return_value = MagicMock(success=True, message="Deleted")

        result = self.service.prepare_handover()

        self.assertTrue(result.success)
        self.mock_manager.delete_connection.assert_called_once_with("netplan-wlan0-Orange Citadel")

    @patch("threading.Thread")
    def test_prepare_handover_deferred(self, mock_thread_cls):
        mock_thread = MagicMock()
        mock_thread_cls.return_value = mock_thread
        self.mock_manager.get_saved_connections.return_value = [
            {"name": "autodarts-MyWiFi", "type": "wifi", "device": "wlan0"}
        ]

        result = self.service.prepare_handover(deferred=True)

        self.assertTrue(result.success)
        self.assertIn("werden gelöscht", result.message)
        mock_thread_cls.assert_called_once()
        mock_thread.start.assert_called_once()

    def test_prepare_handover_partial_failure(self):
        self.mock_manager.get_saved_connections.return_value = [
            {"name": "autodarts-HomeWiFi", "type": "wifi", "device": "wlan0"},
        ]
        self.mock_manager.delete_connection.return_value = MagicMock(
            success=False, message="Permission denied"
        )

        result = self.service.prepare_handover()

        self.assertFalse(result.success)
        self.assertIn("Nicht alle", result.message)

    def test_get_backend_info(self):
        info = self.service.get_backend_info()
        self.assertEqual(info["backend"], "NetworkManager")
        self.assertTrue(info["available"])
        self.assertEqual(info["sudo_prefix"], [])


if __name__ == "__main__":
    unittest.main()