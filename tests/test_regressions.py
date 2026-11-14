"""Regressionstests: Origin-Schutz, WLAN-Backend, API-Routen."""

import io
import json
import subprocess
import unittest
from unittest.mock import MagicMock, patch

from app.adapters.wifi_manager import HotspotConfig, NetworkManagerBackend
from app.services.request_origin import is_same_origin


class ImmediateThread:
    """Runs the thread target synchronously (for deferred background jobs)."""

    def __init__(self, target=None, daemon=None, **_kwargs):
        self._target = target

    def start(self):
        self._target()


class TestRequestOrigin(unittest.TestCase):
    def test_same_origin_allowed(self):
        self.assertTrue(is_same_origin("http://autodarts.local", "autodarts.local"))
        self.assertTrue(is_same_origin("http://192.168.4.1", "192.168.4.1:80"))
        # WebSocket: andere Ports, gleicher Host
        self.assertTrue(is_same_origin("http://autodarts.local", "autodarts.local:8092"))
        self.assertTrue(is_same_origin("http://AutoDarts.Local", "autodarts.local"))

    def test_missing_origin_allowed(self):
        self.assertTrue(is_same_origin(None, "autodarts.local"))

    def test_foreign_origin_rejected(self):
        self.assertFalse(is_same_origin("https://evil.example", "autodarts.local"))
        self.assertFalse(is_same_origin("null", "autodarts.local"))
        self.assertFalse(is_same_origin("http://autodarts.local.evil.example", "autodarts.local"))
        self.assertFalse(is_same_origin("http://autodarts.local", None))


@patch("shutil.which", return_value="/usr/bin/nmcli")
class TestNetworkManagerFixes(unittest.TestCase):
    @patch("app.adapters.wifi_manager.networkmanager.subprocess.run")
    def test_ssid_with_apostrophe_is_passed_unchanged(self, mock_run, _which):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        backend = NetworkManagerBackend()
        backend.connect("wlan0", "Bob's WLAN", "password123")
        add_args = mock_run.call_args_list[1][0][0]
        self.assertEqual(add_args[add_args.index("ssid") + 1], "Bob's WLAN")
        # Dauerbetrieb am Netzteil: WLAN-Stromsparen aus (2 = disable)
        self.assertEqual(add_args[add_args.index("wifi.powersave") + 1], "2")

    @patch("app.adapters.wifi_manager.networkmanager.subprocess.run")
    def test_scan_handles_escaped_colons_hidden_and_duplicates(self, mock_run, _which):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=(
                "Net\\:Work:40:WPA2:2412 MHz:\n"
                ":90:WPA2:2437:\n"
                "Home:50:WPA2:2412:\n"
                "Home:80:WPA2:5180:*\n"
                "Home:30:WPA2:2462:\n"
            ),
            stderr="",
        )
        backend = NetworkManagerBackend()
        networks = {n.ssid: n for n in backend.scan_networks("wlan0", rescan=False)}

        self.assertEqual(set(networks), {"Net:Work", "Home"})
        self.assertEqual(networks["Net:Work"].signal, 40)
        self.assertEqual(networks["Net:Work"].frequency, 2412)
        self.assertEqual(networks["Home"].signal, 80)
        self.assertTrue(networks["Home"].in_use)
        # rescan=False darf keinen Rescan auslösen
        self.assertEqual(mock_run.call_count, 1)

    @patch("app.adapters.wifi_manager.networkmanager.subprocess.run")
    def test_delete_connection_allows_only_wifi_profiles(self, mock_run, _which):
        backend = NetworkManagerBackend()
        ok = subprocess.CompletedProcess([], 0, stdout="", stderr="")

        mock_run.side_effect = [subprocess.CompletedProcess([], 0, stdout="802-11-wireless\n", stderr=""), ok]
        self.assertTrue(backend.delete_connection("netplan-wlan0-Orange Citadel").success)
        self.assertEqual(mock_run.call_args_list[-1][0][0][-3:], ["connection", "delete", "netplan-wlan0-Orange Citadel"])

        mock_run.reset_mock()
        mock_run.side_effect = [subprocess.CompletedProcess([], 0, stdout="802-3-ethernet\n", stderr="")]
        self.assertFalse(backend.delete_connection("netplan-eth0").success)
        self.assertEqual(mock_run.call_count, 1)  # kein "connection delete"

    @patch("app.adapters.wifi_manager.networkmanager.subprocess.run")
    def test_has_uplink_understands_long_type_names(self, mock_run, _which):
        backend = NetworkManagerBackend()
        self.assertTrue(backend.has_uplink([
            {"name": "Wired connection 1", "type": "802-3-ethernet", "device": "eth0", "state": "activated"},
        ]))
        self.assertFalse(backend.has_uplink([
            {"name": "autodarts-hotspot-Autodarts-Setup", "type": "802-11-wireless", "device": "wlan0", "state": "activated"},
        ]))

    @patch("app.adapters.wifi_manager.networkmanager.subprocess.run")
    def test_has_uplink_accepts_lan_managed_by_ifupdown(self, mock_run, _which):
        # Debian: enp1s0 per /etc/network/interfaces -> für NetworkManager "unmanaged".
        mock_run.return_value = subprocess.CompletedProcess(
            [], 0,
            stdout="enp1s0:ethernet:unmanaged\nwlp2s0:wifi:disconnected\nlo:loopback:connected (externally)\n",
            stderr="",
        )
        backend = NetworkManagerBackend()
        with patch.object(NetworkManagerBackend, "_default_route_devices", return_value={"enp1s0"}):
            self.assertTrue(backend.has_uplink([]))
        with patch.object(NetworkManagerBackend, "_default_route_devices", return_value=set()):
            self.assertFalse(backend.has_uplink([]))
        # Ein nicht verwalteter WLAN-Hotspot o. Ä. ohne Default-Route zählt nicht.
        with patch.object(NetworkManagerBackend, "_default_route_devices", return_value={"wg0"}):
            self.assertFalse(backend.has_uplink([]))

    @patch("app.adapters.wifi_manager.networkmanager.time.sleep")
    @patch("app.adapters.wifi_manager.networkmanager.threading.Thread", ImmediateThread)
    @patch("app.adapters.wifi_manager.networkmanager.subprocess.run")
    def test_failed_deferred_connect_deletes_profile_and_restarts_hotspot(self, mock_run, _sleep, _which):
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if "up" in cmd and "autodarts-Home" in cmd:
                # nmcli hängt (falsches Passwort) -> Timeout
                raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout"))
            if "--active" in cmd:
                return MagicMock(returncode=0, stdout="", stderr="")
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_run.side_effect = fake_run
        results = []
        backend = NetworkManagerBackend()
        result = backend.connect(
            "wlan0", "Home", "wrongpass", deferred_activation=True,
            on_result=results.append,
            recovery_hotspot=HotspotConfig(ssid="Autodarts-Setup", password="autodarts123"),
        )

        self.assertTrue(result.success)
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].success)
        flat = [" ".join(c) for c in calls]
        self.assertTrue(any("connection delete autodarts-Home" in c for c in flat[2:]))
        self.assertTrue(any("autodarts-hotspot-Autodarts-Setup" in c and " up " in f" {c} " for c in flat))


class TestMainEndpoints(unittest.TestCase):
    def _handler(self, method, path, headers=None, body=b""):
        from app.main import RequestHandler

        class TestHandler(RequestHandler):
            def __init__(self):
                self.path = path
                self.command = method
                self.headers = headers or {}
                self.client_address = ("10.0.0.5", 1234)
                self.rfile = io.BytesIO(body)
                self.wfile = io.BytesIO()
                self.status = None
                self.sent_headers = {}

            def send_response(self, status, message=None):
                self.status = status

            def send_header(self, name, value):
                self.sent_headers[name] = value

            def end_headers(self):
                pass

        return TestHandler()

    @patch("app.main.shutdown_system")
    def test_cross_origin_post_is_rejected(self, mock_shutdown):
        handler = self._handler("POST", "/api/system/shutdown", {
            "Origin": "https://evil.example", "Host": "autodarts.local",
        })
        handler.do_POST()
        self.assertEqual(handler.status, 403)
        mock_shutdown.assert_not_called()

    @patch("app.main.restart_autodarts", return_value=True)
    def test_same_origin_post_is_accepted(self, _restart):
        handler = self._handler("POST", "/api/autodarts/restart", {
            "Origin": "http://autodarts.local", "Host": "autodarts.local",
        })
        handler.do_POST()
        self.assertEqual(handler.status, 200)

    def test_api_responses_no_longer_allow_any_origin(self):
        handler = self._handler("GET", "/api/system")
        with patch("app.main.get_system_info", return_value={}):
            handler.do_GET()
        self.assertNotIn("Access-Control-Allow-Origin", handler.sent_headers)

    def test_health_keeps_cors_for_hotspot_polling(self):
        handler = self._handler("GET", "/health?t=123")
        handler.do_GET()
        self.assertEqual(handler.status, 200)
        self.assertEqual(handler.sent_headers.get("Access-Control-Allow-Origin"), "*")

    def test_hotspot_phone_check_is_redirected_to_setup_page(self):
        # Android/iOS prüfen beim Verbinden fremde Adressen: Umleitung öffnet
        # die Einrichtungsseite automatisch.
        for host, path in (
            ("connectivitycheck.gstatic.com", "/generate_204"),
            ("captive.apple.com", "/hotspot-detect.html"),
            ("www.msftconnecttest.com", "/connecttest.txt"),
        ):
            handler = self._handler("GET", path, {"Host": host})
            handler.client_address = ("192.168.4.23", 40000)
            handler.do_GET()
            self.assertEqual(handler.status, 302, host)
            self.assertEqual(handler.sent_headers.get("Location"), "http://autodarts.local/")

    def test_health_tells_whether_request_came_via_hotspot(self):
        # Die Startseite darf eine Antwort über den Hotspot nicht als
        # "im Heimnetz erreichbar" werten.
        handler = self._handler("GET", "/health", {"Host": "autodarts.local"})
        handler.client_address = ("192.168.4.23", 40000)
        handler.do_GET()
        self.assertTrue(json.loads(handler.wfile.getvalue())["via_hotspot"])

        handler = self._handler("GET", "/health", {"Host": "autodarts.local"})
        handler.do_GET()
        self.assertFalse(json.loads(handler.wfile.getvalue())["via_hotspot"])

    def test_own_names_and_lan_clients_are_not_redirected(self):
        handler = self._handler("GET", "/admin", {"Host": "192.168.4.1"})
        handler.client_address = ("192.168.4.23", 40000)
        handler.do_GET()
        self.assertEqual(handler.status, 200)

        handler = self._handler("GET", "/admin", {"Host": "autodarts.local:80"})
        handler.client_address = ("192.168.4.23", 40000)
        handler.do_GET()
        self.assertEqual(handler.status, 200)

        # Im Heimnetz nie umleiten, auch nicht bei fremdem Host-Header.
        handler = self._handler("GET", "/admin", {"Host": "example.com"})
        handler.do_GET()
        self.assertEqual(handler.status, 200)

    def test_query_string_does_not_break_page_routes(self):
        handler = self._handler("GET", "/admin?tab=logs")
        handler.do_GET()
        self.assertEqual(handler.status, 200)

    @patch("app.main.create_autodarts_adapter")
    @patch("app.main.subprocess.run")
    def test_autodarts_update_endpoint_no_name_error(self, mock_run, mock_create):
        mock_create.return_value.status.return_value = {"path": "/x/autodarts", "terminal_user": "autodarts"}
        mock_run.return_value = MagicMock(returncode=0, stdout="up to date", stderr="")
        handler = self._handler("POST", "/api/autodarts/update")
        with patch("app.main.os.geteuid", create=True, return_value=1000):
            handler.do_POST()
        self.assertEqual(handler.status, 200)
        self.assertTrue(json.loads(handler.wfile.getvalue())["success"])

    def test_short_wifi_password_rejected(self):
        body = json.dumps({"ssid": "Home", "password": "123"}).encode()
        handler = self._handler("POST", "/api/wifi/connect", {"Content-Length": str(len(body))}, body)
        handler.do_POST()
        self.assertEqual(handler.status, 400)



class TestAutostartEndpoint(unittest.TestCase):
    _handler = TestMainEndpoints._handler

    @patch("app.main.ensure_autodarts_autostart", return_value={"ok": True, "changed": True})
    def test_autostart_endpoint_forces_setup(self, mock_ensure):
        handler = self._handler("POST", "/api/autodarts/autostart", {"Origin": "http://autodarts.local", "Host": "autodarts.local"})
        handler.do_POST()
        self.assertEqual(handler.status, 200)
        mock_ensure.assert_called_once_with(force=True)

    @patch("app.main.ensure_autodarts_autostart", return_value={"ok": False, "reason": "not_installed"})
    def test_autostart_endpoint_reports_error(self, _ensure):
        handler = self._handler("POST", "/api/autodarts/autostart")
        handler.do_POST()
        self.assertEqual(handler.status, 500)
        self.assertEqual(json.loads(handler.wfile.getvalue())["error"], "not_installed")

    def test_terminal_alias_route(self):
        handler = self._handler("GET", "/terminal")
        handler.do_GET()
        self.assertEqual(handler.status, 200)

    def test_shared_stylesheet_is_served(self):
        # Start- und Admin-Seite laden ihre gemeinsame Gestaltung von hier.
        handler = self._handler("GET", "/static/ui.css")
        handler.do_GET()
        self.assertEqual(handler.status, 200)
        self.assertIn(b"--surface", handler.wfile.getvalue())


if __name__ == "__main__":
    unittest.main()
