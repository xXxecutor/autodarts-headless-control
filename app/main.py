import asyncio
import json
import logging
import subprocess
import threading
import os
import platform
import sys
import time
import urllib.parse
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

logger = logging.getLogger(__name__)

from app.adapters.autodarts.factory import create_autodarts_adapter
from app.services.wifi import get_wifi_capabilities
from app.services.autodarts import (
    ensure_autodarts_autostart,
    get_autodarts_status,
    restart_autodarts,
)
from app.services.system import reboot_system, shutdown_system, get_system_logs
from app.services.system_info import get_system_info
from app.services.wifi_manager import WifiManagerService
from app.services.network_watchdog import NetworkWatchdog
from app.services.request_origin import is_same_origin


HOST = "0.0.0.0"
PORT = int(os.environ.get("HEADLESS_HTTP_PORT", "80"))
WEB_ROOT = Path(__file__).resolve().parent / "web"
HOTSPOT_SUBNET_PREFIX = "192.168.4."

# Initialize WiFi Manager Service (singleton for request handlers)
_wifi_manager_service = WifiManagerService()
_network_watchdog = NetworkWatchdog(_wifi_manager_service)

STATIC_FILES = {
    "/static/xterm.js": (
        "xterm.js",
        "application/javascript; charset=utf-8",
    ),
    "/static/xterm.css": (
        "xterm.css",
        "text/css; charset=utf-8",
    ),
    "/static/xterm-addon-fit.js": (
        "xterm-addon-fit.js",
        "application/javascript; charset=utf-8",
    ),
}

HTML_PAGES = {
    "/": "index.html",
    "/index.html": "index.html",
    "/admin": "admin.html",
    "/admin.html": "admin.html",
    "/terminal": "terminal.html",
}

# Nur der Health-Check darf cross-origin gelesen werden: Die Hotspot-Seite
# (http://192.168.4.1) pollt damit http://autodarts.local nach dem WLAN-Wechsel.
CORS_PATHS = {"/health"}


def _serialize_networks(networks):
    return [
        {
            "ssid": n.ssid,
            "signal": n.signal,
            "security": n.security,
            "frequency": n.frequency,
            "in_use": n.in_use,
        }
        for n in networks
    ]


class RequestHandler(BaseHTTPRequestHandler):

    def log_message(self, format: str, *args) -> None:
        # Systemd/journald stellt jeder Ausgabe bereits einen präzisen Zeitstempel voran.
        # Wir unterdrücken das redundante Common-Log-Datum und loggen schlank ohne nachgestellten Bindestrich.
        msg = (format % args).rstrip(" -")
        sys.stderr.write("%s - %s\n" % (self.address_string(), msg))

    # ------------------------------------------------------------------
    # Hilfsfunktionen
    # ------------------------------------------------------------------

    @property
    def route(self) -> str:
        return urllib.parse.urlsplit(self.path).path or "/"

    def _note_client(self) -> None:
        try:
            if self.client_address[0].startswith(HOTSPOT_SUBNET_PREFIX):
                _network_watchdog.note_client_activity()
        except (AttributeError, IndexError, TypeError):
            pass

    def _cors_headers(self) -> None:
        if self.route in CORS_PATHS:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")

    def _json_response(self, data, status=200):
        body = json.dumps(data).encode("utf-8")

        self.send_response(status)
        self.send_header(
            "Content-Type",
            "application/json; charset=utf-8",
        )
        self.send_header("Cache-Control", "no-store")
        self._cors_headers()
        self.send_header(
            "Content-Length",
            str(len(body)),
        )
        self.end_headers()

        self.wfile.write(body)

    def _file_response(self, filename: str, content_type: str) -> None:
        try:
            body = (WEB_ROOT / filename).read_bytes()
        except OSError:
            self.send_response(404 if filename.startswith("xterm") else 500)
            self.end_headers()
            return

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        # Nach automatischen Updates soll der Browser keine alte Oberfläche zeigen.
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _not_found(self) -> None:
        self.send_response(404)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    # ------------------------------------------------------------------
    # GET
    # ------------------------------------------------------------------

    def do_GET(self):
        self._note_client()
        route = self.route

        if route in STATIC_FILES:
            filename, content_type = STATIC_FILES[route]
            self._file_response(filename, content_type)
            return

        if route in HTML_PAGES:
            self._file_response(HTML_PAGES[route], "text/html; charset=utf-8")
            return

        if route == "/health":
            self._json_response({"status": "ok"})
            return

        if route == "/api/system":
            self._json_response(get_system_info())
            return

        if route == "/api/wifi/capabilities":
            try:
                capabilities = get_wifi_capabilities()
            except RuntimeError as exc:
                self._json_response(
                    {
                        "supported": False,
                        "error": str(exc),
                    },
                    501,
                )
                return

            self._json_response(capabilities)
            return

        if route == "/api/wifi/state":
            try:
                state = _wifi_manager_service.get_network_state()
                self._json_response({
                    "decision": state.decision.value,
                    "active_connections": state.active_connections,
                    "available_networks": _serialize_networks(state.available_networks),
                    "hotspot_active": state.hotspot_active,
                    "last_connect": _wifi_manager_service.last_connect_result,
                    "backend": _wifi_manager_service.get_backend_info(),
                })
            except Exception as exc:
                logger.exception("GET /api/wifi/state failed")
                self._json_response({"error": str(exc)}, 500)
            return

        if route == "/api/wifi/backend":
            try:
                self._json_response(_wifi_manager_service.get_backend_info())
            except Exception as exc:
                self._json_response({"error": str(exc)}, 500)
            return

        if route == "/api/autodarts":
            try:
                status = get_autodarts_status()
            except RuntimeError as exc:
                self._json_response(
                    {
                        "supported": False,
                        "error": str(exc),
                    },
                    501,
                )
                return

            self._json_response(status)
            return

        if route == "/api/system/logs":
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            target = query.get("target", ["app"])[0]
            raw_lines = query.get("lines", ["50"])[0]
            try:
                line_count = int(raw_lines)
            except ValueError:
                line_count = 50

            try:
                logs = get_system_logs(target=target, lines=line_count)
                self._json_response({
                    "status": "ok",
                    "target": target,
                    "lines": line_count,
                    "logs": logs,
                })
            except Exception as exc:
                self._json_response({"status": "error", "error": str(exc)}, 500)
            return

        self._not_found()

    # ------------------------------------------------------------------
    # POST
    # ------------------------------------------------------------------

    def _parse_json_body(self):
        """Parse JSON request body."""
        try:
            content_length = int(self.headers.get("Content-Length", 0) or 0)
        except ValueError:
            return {}
        if content_length <= 0 or content_length > 64 * 1024:
            return {}
        body = self.rfile.read(content_length)
        try:
            data = json.loads(body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def do_POST(self):
        self._note_client()

        # Schutz vor Cross-Site-Requests: Fremde Webseiten dürfen die Box
        # nicht herunterfahren, WLAN-Profile löschen o. Ä.
        if not is_same_origin(self.headers.get("Origin"), self.headers.get("Host")):
            logger.warning("Rejected cross-origin POST %s from Origin %s", self.route, self.headers.get("Origin"))
            self._json_response({"success": False, "error": "Cross-origin request rejected"}, 403)
            return

        route = self.route

        if route == "/api/autodarts/restart":
            success = restart_autodarts()
            self._json_response(
                {"success": success},
                200 if success else 500,
            )
            return

        if route == "/api/autodarts/autostart":
            try:
                result = ensure_autodarts_autostart(force=True)
            except RuntimeError as exc:
                result = {"ok": False, "reason": str(exc)}
            if not result.get("ok"):
                result["error"] = result.get("reason", "unknown")
            self._json_response(result, 200 if result.get("ok") else 500)
            return

        if route == "/api/system/reboot":
            self._json_response({"success": True}, 200)
            def _bg_reboot():
                time.sleep(0.5)
                logger.info("Executing system reboot request...")
                ok = reboot_system()
                logger.info("reboot_system finished with status: %s", ok)
            threading.Thread(target=_bg_reboot, daemon=True).start()
            return

        if route == "/api/system/shutdown":
            self._json_response({"success": True}, 200)
            def _bg_shutdown():
                time.sleep(0.5)
                logger.info("Executing system shutdown request...")
                ok = shutdown_system()
                logger.info("shutdown_system finished with status: %s", ok)
            threading.Thread(target=_bg_shutdown, daemon=True).start()
            return

        # WiFi API endpoints
        if route == "/api/wifi/scan":
            try:
                networks = _wifi_manager_service.scan(rescan=True)
                self._json_response({"networks": _serialize_networks(networks)})
            except Exception as exc:
                logger.exception("POST /api/wifi/scan failed")
                self._json_response({"error": str(exc)}, 500)
            return

        if route == "/api/wifi/connect":
            try:
                data = self._parse_json_body()
                ssid = data.get("ssid")
                password = data.get("password", "") or ""
                if not isinstance(ssid, str) or not ssid.strip():
                    self._json_response({"success": False, "error": "SSID required"}, 400)
                    return
                # WPA-PSK: 8–63 Zeichen Passphrase oder 64 Hex-Zeichen.
                if not isinstance(password, str) or (password and not 8 <= len(password) <= 64):
                    self._json_response(
                        {"success": False, "error": "WLAN-Passwort muss 8 bis 64 Zeichen lang sein (leer = offenes Netz)."},
                        400,
                    )
                    return
                result = _wifi_manager_service.connect_to_wifi(ssid, password)
                self._json_response(
                    {"success": result.success, "message": result.message, "connection_name": result.connection_name},
                    200 if result.success else 400,
                )
            except Exception as exc:
                logger.exception("POST /api/wifi/connect failed")
                self._json_response({"success": False, "error": str(exc)}, 500)
            return

        if route == "/api/wifi/hotspot/start":
            try:
                data = self._parse_json_body()
                ssid = data.get("ssid", "Autodarts-Setup")
                password = data.get("password", "autodarts123")
                from app.adapters.wifi_manager import HotspotConfig
                config = HotspotConfig(ssid=ssid, password=password)
                result = _wifi_manager_service.start_hotspot_manual(config, deferred=True)
                self._json_response(
                    {"success": result.success, "message": result.message, "connection_name": result.connection_name},
                    200 if result.success else 400,
                )
            except Exception as exc:
                logger.exception("POST /api/wifi/hotspot/start failed")
                self._json_response({"success": False, "error": str(exc)}, 500)
            return

        if route == "/api/wifi/hotspot/stop":
            try:
                data = self._parse_json_body()
                connection_name = data.get("connection_name")
                manager_active = _wifi_manager_service._get_manager().get_active_connections()
                interface = None

                # If connection_name not given, find any active hotspot connection
                if not connection_name:
                    hotspot = _wifi_manager_service.find_hotspot(manager_active)
                    if hotspot:
                        connection_name = hotspot["name"]
                        interface = hotspot.get("device")

                # Resolve interface for given connection_name if not yet found
                if connection_name and not interface:
                    for conn in manager_active:
                        if conn.get("name") == connection_name:
                            interface = conn.get("device")
                            break

                if not connection_name:
                    connection_name = "autodarts-hotspot-Autodarts-Setup"

                if not interface:
                    interfaces = _wifi_manager_service.wireless_interfaces()
                    interface = interfaces[0] if interfaces else "wlan0"

                result = _wifi_manager_service.stop_hotspot(connection_name, interface, deferred=True)
                self._json_response(
                    {"success": result.success, "message": result.message},
                    200 if result.success else 400,
                )
            except Exception as exc:
                logger.exception("POST /api/wifi/hotspot/stop failed")
                self._json_response({"success": False, "error": str(exc)}, 500)
            return

        if route == "/api/wifi/handover":
            try:
                result = _wifi_manager_service.prepare_handover(deferred=True)
                self._json_response(
                    {"success": result.success, "message": result.message},
                    200 if result.success else 400,
                )
            except Exception as exc:
                logger.exception("POST /api/wifi/handover failed")
                self._json_response({"success": False, "error": str(exc)}, 500)
            return

        if route == "/api/autodarts/update":
            try:
                # Run autodarts update as autodarts user
                adapter = create_autodarts_adapter()
                status = adapter.status()
                autodarts_bin = status.get("path") or "/var/lib/autodarts-headless-control/.local/bin/autodarts"
                user = status.get("terminal_user") or "autodarts"
                if os.geteuid() == 0:
                    cmd = ["sudo", "-u", user, autodarts_bin, "update"]
                else:
                    cmd = [autodarts_bin, "update"]

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                success = result.returncode == 0
                self._json_response(
                    {
                        "success": success,
                        "message": result.stdout.strip() if success else result.stderr.strip(),
                        "output": result.stdout.strip(),
                    },
                    200 if success else 500,
                )
            except subprocess.TimeoutExpired:
                self._json_response({"success": False, "error": "Update timed out"}, 500)
            except Exception as exc:
                self._json_response({"success": False, "error": str(exc)}, 500)
            return

        self._not_found()


def _setup_autodarts_autostart():
    """Einmalig nach dem Start: Autodarts als Hintergrunddienst einrichten.

    So läuft das Board nach jedem Einschalten, ohne dass jemand in der
    Autodarts-TUI "Run as a service" anhaken muss.
    """
    time.sleep(5)
    try:
        result = ensure_autodarts_autostart()
        logger.info("Autodarts autostart check: %s", result)
    except Exception:
        logger.exception("Autodarts autostart setup failed")


def start_websocket_server():
    from app.services.terminal_server import websocket_server

    asyncio.run(websocket_server())


def main():
    logging.basicConfig(
        level=os.environ.get("HEADLESS_LOG_LEVEL", "INFO").upper(),
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    websocket_thread = threading.Thread(
        target=start_websocket_server,
        daemon=True,
        name="terminal-websocket",
    )

    websocket_thread.start()

    if platform.system() == "Linux" and os.environ.get("HEADLESS_HOTSPOT_FALLBACK", "1") != "0":
        _network_watchdog.start()

    if platform.system() == "Linux" and os.environ.get("HEADLESS_AUTODARTS_AUTOSTART", "1") != "0":
        threading.Thread(target=_setup_autodarts_autostart, daemon=True, name="autodarts-autostart").start()

    server = ThreadingHTTPServer(
        (HOST, PORT),
        RequestHandler,
    )

    print(
        f"Headless Control läuft auf "
        f"http://{HOST}:{PORT}"
    )

    try:
        server.serve_forever()

    except KeyboardInterrupt:
        pass

    finally:
        server.server_close()


if __name__ == "__main__":
    main()
