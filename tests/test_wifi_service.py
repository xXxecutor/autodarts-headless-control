import unittest
from unittest.mock import patch

from app.services.wifi import get_wifi_capabilities


class TestWifiService(unittest.TestCase):
    @patch(
        "app.services.wifi.create_wifi_adapter"
    )
    def test_returns_adapter_capabilities(self, mock_create_adapter):
        expected = {
            "supported_platform": True,
            "tools": {"nmcli": "/usr/bin/nmcli"},
            "network_manager": "NetworkManager",
        }
        mock_create_adapter.return_value.detect.return_value = expected

        self.assertEqual(get_wifi_capabilities(), expected)
        mock_create_adapter.assert_called_once()
        mock_create_adapter.return_value.detect.assert_called_once()


if __name__ == "__main__":
    unittest.main()
