import unittest
from app.services.network_policy import (
    NetworkDecision,
    decide_network_action,
    _is_ethernet_interface,
    _is_wireless_interface,
    _has_active_ip,
    _is_interface_up,
)


class TestNetworkPolicyHelpers(unittest.TestCase):
    def test_is_ethernet_interface(self):
        self.assertTrue(_is_ethernet_interface("eth0"))
        self.assertTrue(_is_ethernet_interface("eno1"))
        self.assertTrue(_is_ethernet_interface("enp3s0"))
        self.assertTrue(_is_ethernet_interface("enx001122334455"))
        self.assertTrue(_is_ethernet_interface("ens33"))
        self.assertFalse(_is_ethernet_interface("wlan0"))
        self.assertFalse(_is_ethernet_interface("wlp2s0"))
        self.assertFalse(_is_ethernet_interface("lo"))

    def test_is_wireless_interface(self):
        self.assertTrue(_is_wireless_interface("wlan0"))
        self.assertTrue(_is_wireless_interface("wlp2s0"))
        self.assertTrue(_is_wireless_interface("wifi0"))
        self.assertFalse(_is_wireless_interface("eth0"))
        self.assertFalse(_is_wireless_interface("eno1"))
        self.assertFalse(_is_wireless_interface("lo"))

    def test_has_active_ip(self):
        self.assertTrue(_has_active_ip({"addresses": ["192.168.1.10/24"]}))
        self.assertTrue(_has_active_ip({"addresses": ["10.0.0.5/24", "fe80::1/64"]}))
        self.assertFalse(_has_active_ip({"addresses": []}))
        self.assertFalse(_has_active_ip({}))
        self.assertFalse(_has_active_ip({"addresses": None}))

    def test_is_interface_up(self):
        self.assertTrue(_is_interface_up({"state": "UP"}))
        self.assertFalse(_is_interface_up({"state": "DOWN"}))
        self.assertFalse(_is_interface_up({"state": "UNKNOWN"}))
        self.assertFalse(_is_interface_up({}))


class TestNetworkPolicyDecisions(unittest.TestCase):
    def base_detect(self, **overrides):
        """Build a base detect_result with sensible defaults."""
        base = {
            "supported_platform": True,
            "tools": {"ip": "/usr/sbin/ip", "iw": "/usr/sbin/iw", "nmcli": "/usr/bin/nmcli"},
            "network_manager": "NetworkManager",
            "wireless": {"interfaces": ["wlan0"], "wireless_visible": True},
            "access_point_support": "supported",
            "network_status": {
                "available": True,
                "interfaces": [],
                "connected": False,
            },
        }
        base.update(overrides)
        return base

    def test_keep_ethernet_when_active_with_ip(self):
        """Active Ethernet with IP -> KEEP_ETHERNET (highest priority)."""
        detect = self.base_detect(
            network_status={
                "available": True,
                "interfaces": [
                    {"name": "eth0", "state": "UP", "addresses": ["192.168.1.20/24"]},
                    {"name": "wlan0", "state": "UP", "addresses": ["192.168.1.21/24"]},
                ],
                "connected": True,
            },
        )
        self.assertEqual(decide_network_action(detect), NetworkDecision.KEEP_ETHERNET)

    def test_keep_ethernet_priority_over_wifi(self):
        """Ethernet takes priority even when WiFi also has IP."""
        detect = self.base_detect(
            network_status={
                "available": True,
                "interfaces": [
                    {"name": "eth0", "state": "UP", "addresses": ["192.168.1.20/24"]},
                    {"name": "wlan0", "state": "UP", "addresses": ["192.168.1.21/24"]},
                ],
                "connected": True,
            },
        )
        self.assertEqual(decide_network_action(detect), NetworkDecision.KEEP_ETHERNET)

    def test_keep_ethernet_various_naming(self):
        """Different Ethernet interface naming schemes."""
        for name in ["eth0", "eno1", "enp3s0", "enx001122334455", "ens33"]:
            detect = self.base_detect(
                network_status={
                    "available": True,
                    "interfaces": [{"name": name, "state": "UP", "addresses": ["192.168.1.20/24"]}],
                    "connected": True,
                },
            )
            self.assertEqual(decide_network_action(detect), NetworkDecision.KEEP_ETHERNET, f"Failed for {name}")

    def test_ethernet_up_without_ip_is_not_connected(self):
        """Ethernet UP but no IP -> not KEEP_ETHERNET, falls through to WiFi/AP."""
        detect = self.base_detect(
            network_status={
                "available": True,
                "interfaces": [{"name": "eth0", "state": "UP", "addresses": []}],
                "connected": False,
            },
            access_point_support="supported",
        )
        # No active IP on Ethernet, no WiFi IP -> should go to hotspot
        self.assertEqual(decide_network_action(detect), NetworkDecision.START_HOTSPOT)

    def test_connect_wifi_when_wireless_active_with_ip(self):
        """Active Wireless with IP (no Ethernet) -> CONNECT_WIFI."""
        detect = self.base_detect(
            network_status={
                "available": True,
                "interfaces": [{"name": "wlan0", "state": "UP", "addresses": ["192.168.1.21/24"]}],
                "connected": True,
            },
        )
        self.assertEqual(decide_network_action(detect), NetworkDecision.CONNECT_WIFI)

    def test_connect_wifi_various_naming(self):
        """Different Wireless interface naming schemes."""
        for name in ["wlan0", "wlp2s0", "wifi0"]:
            detect = self.base_detect(
                network_status={
                    "available": True,
                    "interfaces": [{"name": name, "state": "UP", "addresses": ["192.168.1.21/24"]}],
                    "connected": True,
                },
            )
            self.assertEqual(decide_network_action(detect), NetworkDecision.CONNECT_WIFI, f"Failed for {name}")

    def test_wireless_up_without_ip_falls_to_hotspot(self):
        """Wireless UP but no IP -> not CONNECT_WIFI, falls to hotspot if supported."""
        detect = self.base_detect(
            network_status={
                "available": True,
                "interfaces": [{"name": "wlan0", "state": "UP", "addresses": []}],
                "connected": False,
            },
            access_point_support="supported",
        )
        self.assertEqual(decide_network_action(detect), NetworkDecision.START_HOTSPOT)

    def test_start_hotspot_when_no_connection_but_ap_supported(self):
        """No active connection, AP supported -> START_HOTSPOT."""
        detect = self.base_detect(
            network_status={
                "available": True,
                "interfaces": [
                    {"name": "eth0", "state": "DOWN", "addresses": []},
                    {"name": "wlan0", "state": "DOWN", "addresses": []},
                ],
                "connected": False,
            },
            access_point_support="supported",
        )
        self.assertEqual(decide_network_action(detect), NetworkDecision.START_HOTSPOT)

    def test_start_hotspot_when_network_status_unavailable_but_ap_supported(self):
        """network_status unavailable but AP supported -> START_HOTSPOT."""
        detect = self.base_detect(
            network_status={"available": False, "interfaces": [], "connected": None},
            access_point_support="supported",
        )
        self.assertEqual(decide_network_action(detect), NetworkDecision.START_HOTSPOT)

    def test_error_no_network_when_ap_unsupported(self):
        """No connection, AP unsupported -> ERROR_NO_NETWORK."""
        detect = self.base_detect(
            network_status={
                "available": True,
                "interfaces": [
                    {"name": "eth0", "state": "DOWN", "addresses": []},
                    {"name": "wlan0", "state": "DOWN", "addresses": []},
                ],
                "connected": False,
            },
            access_point_support="unsupported",
        )
        self.assertEqual(decide_network_action(detect), NetworkDecision.ERROR_NO_NETWORK)

    def test_error_no_network_when_ap_unknown(self):
        """No connection, AP unknown -> ERROR_NO_NETWORK (conservative)."""
        detect = self.base_detect(
            network_status={
                "available": True,
                "interfaces": [
                    {"name": "eth0", "state": "DOWN", "addresses": []},
                    {"name": "wlan0", "state": "DOWN", "addresses": []},
                ],
                "connected": False,
            },
            access_point_support="unknown",
        )
        self.assertEqual(decide_network_action(detect), NetworkDecision.ERROR_NO_NETWORK)

    def test_error_no_network_when_no_wireless_hardware(self):
        """No wireless hardware visible, no Ethernet, no AP -> ERROR_NO_NETWORK."""
        detect = self.base_detect(
            wireless={"interfaces": [], "wireless_visible": False},
            network_status={
                "available": True,
                "interfaces": [{"name": "eth0", "state": "DOWN", "addresses": []}],
                "connected": False,
            },
            access_point_support="unknown",
        )
        self.assertEqual(decide_network_action(detect), NetworkDecision.ERROR_NO_NETWORK)

    def test_error_no_network_on_unsupported_platform(self):
        """Non-Linux platform -> ERROR_NO_NETWORK."""
        detect = {
            "supported_platform": False,
            "tools": {},
            "network_manager": None,
            "wireless": {"interfaces": [], "wireless_visible": False},
            "access_point_support": "unknown",
            "network_status": {"available": False, "interfaces": [], "connected": None},
        }
        self.assertEqual(decide_network_action(detect), NetworkDecision.ERROR_NO_NETWORK)

    def test_wireless_visible_but_no_ap_and_no_ip_is_error(self):
        """Wireless hardware exists but not connected and AP unsupported -> ERROR."""
        detect = self.base_detect(
            network_status={
                "available": True,
                "interfaces": [{"name": "wlan0", "state": "DOWN", "addresses": []}],
                "connected": False,
            },
            access_point_support="unsupported",
        )
        self.assertEqual(decide_network_action(detect), NetworkDecision.ERROR_NO_NETWORK)

    def test_lo_interface_ignored(self):
        """Loopback interface should not affect decision."""
        detect = self.base_detect(
            network_status={
                "available": True,
                "interfaces": [
                    {"name": "lo", "state": "UNKNOWN", "addresses": ["127.0.0.1/8", "::1/128"]},
                    {"name": "eth0", "state": "DOWN", "addresses": []},
                ],
                "connected": False,
            },
            access_point_support="supported",
        )
        self.assertEqual(decide_network_action(detect), NetworkDecision.START_HOTSPOT)


if __name__ == "__main__":
    unittest.main()