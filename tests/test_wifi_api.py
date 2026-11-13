import json
import unittest
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler

from app.main import RequestHandler


class TestWifiApi(unittest.TestCase):
    def test_wifi_capabilities_endpoint(self):
        expected = {
            "supported_platform": True,
            "tools": {"ip": "/usr/sbin/ip"},
            "network_manager": None,
        }

        class TestHandler(RequestHandler):
            def __init__(self):
                self.path = "/api/wifi/capabilities"
                self.response_status = None
                self.response_headers = {}
                self.response_body = b""

            def send_response(self, status, message=None):
                self.response_status = status

            def send_header(self, name, value):
                self.response_headers[name] = value

            def end_headers(self):
                pass

        handler = TestHandler()
        handler.wfile = type("Writer", (), {
            "write": lambda _self, body: setattr(
                handler, "response_body", body
            )
        })()

        with patch(
            "app.main.get_wifi_capabilities",
            return_value=expected,
        ):
            handler.do_GET()

        self.assertEqual(handler.response_status, 200)
        self.assertEqual(
            json.loads(handler.response_body.decode("utf-8")),
            expected,
        )

    def test_wifi_capabilities_without_wireless_interface(self):
        expected = {
            "supported_platform": True,
            "tools": {"ip": "/usr/sbin/ip"},
            "network_manager": None,
            "wireless": {
                "interfaces": [],
                "wireless_visible": False,
            },
            "access_point_support": "unknown",
        }

        class TestHandler(RequestHandler):
            def __init__(self):
                self.path = "/api/wifi/capabilities"
                self.response_status = None
                self.response_headers = {}
                self.response_body = b""

            def send_response(self, status, message=None):
                self.response_status = status

            def send_header(self, name, value):
                self.response_headers[name] = value

            def end_headers(self):
                pass

        handler = TestHandler()
        handler.wfile = type("Writer", (), {
            "write": lambda _self, body: setattr(
                handler, "response_body", body
            )
        })()

        with patch(
            "app.main.get_wifi_capabilities",
            return_value=expected,
        ):
            handler.do_GET()

        self.assertEqual(handler.response_status, 200)
        actual = json.loads(handler.response_body.decode("utf-8"))
        self.assertEqual(actual, expected)
        self.assertEqual(actual["wireless"]["interfaces"], [])
        self.assertEqual(actual["access_point_support"], "unknown")

if __name__ == "__main__":
    unittest.main()
