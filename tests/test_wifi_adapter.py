import unittest
from unittest.mock import patch

from app.adapters.wifi.linux import LinuxWifiAdapter


class TestLinuxWifiAdapter(unittest.TestCase):
    @patch("app.adapters.wifi.linux.platform.system", return_value="Linux")
    @patch("app.adapters.wifi.linux.shutil.which")
    def test_detects_available_tools(self, mock_which, _mock_platform):
        mock_which.side_effect = lambda name: {
            "nmcli": "/usr/bin/nmcli",
            "ip": "/usr/sbin/ip",
        }.get(name)

        result = LinuxWifiAdapter().detect()

        self.assertTrue(result["supported_platform"])
        self.assertEqual(result["network_manager"], "NetworkManager")
        self.assertEqual(result["tools"]["nmcli"], "/usr/bin/nmcli")
        self.assertEqual(result["tools"]["ip"], "/usr/sbin/ip")
        self.assertIsNone(result["tools"]["iw"])

    @patch("app.adapters.wifi.linux.platform.system", return_value="Linux")
    @patch("app.adapters.wifi.linux.shutil.which", return_value=None)
    def test_handles_missing_tools(self, _mock_which, _mock_platform):
        result = LinuxWifiAdapter().detect()

        self.assertTrue(result["supported_platform"])
        self.assertIsNone(result["network_manager"])
        self.assertTrue(all(path is None for path in result["tools"].values()))

    @patch("app.adapters.wifi.linux.platform.system", return_value="Windows")
    def test_rejects_non_linux_platform(self, _mock_platform):
        result = LinuxWifiAdapter().detect()

        self.assertFalse(result["supported_platform"])
        self.assertEqual(result["tools"], {})
        self.assertIsNone(result["network_manager"])
    
    @patch("app.adapters.wifi.linux.platform.system", return_value="Linux")
    def test_detects_wireless_interface(self, _mock_platform):
        from pathlib import Path
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "wlan0" / "wireless").mkdir(parents=True)

            with patch.object(LinuxWifiAdapter, "NET_ROOT", root):
                result = LinuxWifiAdapter().detect_wireless_interfaces()

        self.assertTrue(result["supported_platform"])
        self.assertEqual(result["interfaces"], ["wlan0"])
        self.assertTrue(result["wireless_visible"])

    @patch("app.adapters.wifi.linux.platform.system", return_value="Linux")
    def test_no_wireless_interface_visible(self, _mock_platform):
        from pathlib import Path
        with patch.object(Path, "iterdir", return_value=[]):
            result = LinuxWifiAdapter().detect_wireless_interfaces()

        self.assertTrue(result["supported_platform"])
        self.assertEqual(result["interfaces"], [])
        self.assertFalse(result["wireless_visible"])

    @patch("subprocess.run")
    def test_detects_access_point_support(self, mock_run):
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = (
            "Supported interface modes:\n"
            "\t * managed\n"
            "\t * AP\n"
        )

        result = LinuxWifiAdapter().detect_access_point_support(
            ["wlan0"],
            "/usr/sbin/iw",
        )

        self.assertEqual(result, "supported")

    @patch("subprocess.run")
    def test_detects_unsupported_access_point_mode(self, mock_run):
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = (
            "Supported interface modes:\n"
            "\t * managed\n"
        )

        result = LinuxWifiAdapter().detect_access_point_support(
            ["wlan0"],
            "/usr/sbin/iw",
        )

        self.assertEqual(result, "unsupported")

    def test_access_point_support_unknown_without_interface_or_iw(self):
        adapter = LinuxWifiAdapter()

        self.assertEqual(
            adapter.detect_access_point_support([], "/usr/sbin/iw"),
            "unknown",
        )
        self.assertEqual(
            adapter.detect_access_point_support(["wlan0"], None),
            "unknown",
        )

    @patch("subprocess.run",
        side_effect=OSError("iw unavailable"),
    )
    def test_access_point_support_unknown_on_command_error(self, _mock_run):
        result = LinuxWifiAdapter().detect_access_point_support(
            ["wlan0"],
            "/usr/sbin/iw",
        )

        self.assertEqual(result, "unknown")

    @patch("subprocess.run")
    def test_detects_active_network_with_ip_address(self, mock_run):
        mock_run.side_effect = [
            type("Result", (), {
                "returncode": 0,
                "stdout": "eth0 UP 00:11:22:33:44:55\n",
            })(),
            type("Result", (), {
                "returncode": 0,
                "stdout": "eth0 UP 192.168.1.20/24\n",
            })(),
        ]

        result = LinuxWifiAdapter().detect_network_status("/usr/sbin/ip")

        self.assertTrue(result["available"])
        self.assertTrue(result["connected"])
        self.assertEqual(result["interfaces"][0]["name"], "eth0")
        self.assertEqual(
            result["interfaces"][0]["addresses"],
            ["192.168.1.20/24"],
        )

    @patch("subprocess.run")
    def test_detects_no_active_network_connection(self, mock_run):
        mock_run.side_effect = [
            type("Result", (), {
                "returncode": 0,
                "stdout": "wlan0 DOWN 00:11:22:33:44:55\n",
            })(),
            type("Result", (), {
                "returncode": 0,
                "stdout": "wlan0 DOWN\n",
            })(),
        ]

        result = LinuxWifiAdapter().detect_network_status("/usr/sbin/ip")

        self.assertTrue(result["available"])
        self.assertFalse(result["connected"])

    def test_network_status_unavailable_without_ip_tool(self):
        result = LinuxWifiAdapter().detect_network_status(None)

        self.assertFalse(result["available"])
        self.assertIsNone(result["connected"])
        self.assertEqual(result["interfaces"], [])

    @patch("subprocess.run")
    def test_distinguishes_ethernet_and_wifi_interfaces(self, mock_run):
        mock_run.side_effect = [
            type("Result", (), {
                "returncode": 0,
                "stdout": (
                    "lo UNKNOWN 00:00:00:00:00:00\n"
                    "eth0 UP 00:11:22:33:44:55\n"
                    "wlan0 UP aa:bb:cc:dd:ee:ff\n"
                ),
            })(),
            type("Result", (), {
                "returncode": 0,
                "stdout": (
                    "lo UNKNOWN 127.0.0.1/8 ::1/128\n"
                    "eth0 UP 192.168.1.20/24\n"
                    "wlan0 UP 192.168.1.21/24\n"
                ),
            })(),
        ]

        result = LinuxWifiAdapter().detect_network_status("/usr/sbin/ip")

        self.assertTrue(result["connected"])
        self.assertEqual(
            [item["name"] for item in result["interfaces"]],
            ["eth0", "wlan0"],
        )
        self.assertEqual(
            result["interfaces"][0]["addresses"],
            ["192.168.1.20/24"],
        )
        self.assertEqual(
            result["interfaces"][1]["addresses"],
            ["192.168.1.21/24"],
        )

    @patch("subprocess.run")
    def test_interface_up_without_ip_is_not_connected(self, mock_run):
        mock_run.side_effect = [
            type("Result", (), {
                "returncode": 0,
                "stdout": "eth0 UP 00:11:22:33:44:55\n",
            })(),
            type("Result", (), {
                "returncode": 0,
                "stdout": "eth0 UP\n",
            })(),
        ]

        result = LinuxWifiAdapter().detect_network_status("/usr/sbin/ip")

        self.assertTrue(result["available"])
        self.assertFalse(result["connected"])

    @patch("subprocess.run")
    def test_ethernet_connection_is_detected_without_wifi(self, mock_run):
        mock_run.side_effect = [
            type("Result", (), {
                "returncode": 0,
                "stdout": "eth0 UP 00:11:22:33:44:55\n",
            })(),
            type("Result", (), {
                "returncode": 0,
                "stdout": "eth0 UP 192.168.1.20/24\n",
            })(),
        ]

        result = LinuxWifiAdapter().detect_network_status("/usr/sbin/ip")

        self.assertTrue(result["connected"])
        self.assertEqual(len(result["interfaces"]), 1)
        self.assertEqual(result["interfaces"][0]["name"], "eth0")

if __name__ == "__main__":
    unittest.main()