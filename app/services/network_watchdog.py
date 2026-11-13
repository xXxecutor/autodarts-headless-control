"""Automatischer Setup-Hotspot (Fallback) und Rückkehr ins bekannte WLAN.

Ablauf:
1. Nach dem Start (bzw. nach Verlust der letzten Verbindung) wird ``grace``
   Sekunden gewartet, damit NetworkManager bekannte Netze selbst verbinden kann.
2. Gibt es danach weder Ethernet noch WLAN, wird der Hotspot gestartet.
3. Läuft der Hotspot ``retry_interval`` Sekunden ohne verbundene Clients und
   existieren gespeicherte WLAN-Profile, wird der Hotspot kurz beendet und das
   bekannte WLAN erneut versucht (z. B. Router nach Stromausfall langsamer).
   Klappt das nicht, startet der Hotspot sofort wieder.
"""

import logging
import os
import shutil
import subprocess
import threading
import time
from typing import Callable

logger = logging.getLogger(__name__)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


class NetworkWatchdog:
    def __init__(
        self,
        service,
        grace: int | None = None,
        retry_interval: int | None = None,
        poll_interval: int = 10,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.service = service
        self.grace = grace if grace is not None else _env_int("HEADLESS_HOTSPOT_GRACE", 45)
        self.retry_interval = (
            retry_interval if retry_interval is not None
            else _env_int("HEADLESS_HOTSPOT_RETRY", 300)
        )
        self.poll_interval = poll_interval
        self._clock = clock

        self.started = clock()
        self.last_uplink: float | None = None
        self.hotspot_since: float | None = None
        self.last_client_seen: float | None = None
        self._stop = threading.Event()

    # ------------------------------------------------------------------

    def note_client_activity(self) -> None:
        """Called by the HTTP server for requests arriving via the hotspot."""
        self.last_client_seen = self._clock()

    def _hotspot_has_clients(self, interface: str) -> bool:
        iw = shutil.which("iw")
        if iw:
            try:
                res = subprocess.run(
                    [iw, "dev", interface, "station", "dump"],
                    capture_output=True, text=True, timeout=5, check=False,
                )
                if res.returncode == 0:
                    return any(line.startswith("Station ") for line in res.stdout.splitlines())
            except (OSError, subprocess.SubprocessError):
                pass

        ip = shutil.which("ip")
        if ip:
            try:
                res = subprocess.run(
                    [ip, "neigh", "show", "dev", interface],
                    capture_output=True, text=True, timeout=5, check=False,
                )
                if res.returncode == 0:
                    return any(
                        state in line
                        for line in res.stdout.splitlines()
                        for state in ("REACHABLE", "DELAY", "PROBE")
                    )
            except (OSError, subprocess.SubprocessError):
                pass
        return False

    # ------------------------------------------------------------------

    def tick(self) -> str:
        """Run one evaluation step; returns a short state label (for tests/logs)."""
        service = self.service
        if service.is_busy():
            return "busy"
        if not service.lock.acquire(blocking=False):
            return "busy"
        try:
            return self._tick_locked()
        finally:
            service.lock.release()

    def _tick_locked(self) -> str:
        service = self.service
        now = self._clock()
        manager = service._get_manager()
        if not manager.is_available():
            return "no_backend"

        detect = service.refresh_detection()
        interfaces = service.wireless_interfaces(detect)
        active = manager.get_active_connections()
        hotspot = service.find_hotspot(active)

        if manager.has_uplink(active):
            self.last_uplink = now
            if hotspot is None:
                self.hotspot_since = None
            return "online"

        if hotspot is not None:
            if self.hotspot_since is None:
                self.hotspot_since = now
            interface = hotspot.get("device") or (interfaces[0] if interfaces else "")
            if interface and self._hotspot_has_clients(interface):
                self.last_client_seen = now

            idle_since = max(self.hotspot_since, self.last_client_seen or 0.0)
            if now - idle_since < self.retry_interval:
                return "hotspot"
            if not interface or not service.has_saved_wifi_profiles():
                return "hotspot"

            logger.info("Hotspot idle for %ss; retrying known Wi-Fi on %s", int(now - idle_since), interface)
            manager.stop_hotspot(interface, hotspot["name"])
            self.hotspot_since = None
            if manager.connect_known(interface) and manager.has_uplink():
                logger.info("Reconnected to known Wi-Fi; setup hotspot stays off")
                self.last_uplink = self._clock()
                return "reconnected"

            logger.info("Known Wi-Fi still unavailable; restarting setup hotspot")
            result = service.start_fallback_hotspot(interface)
            if not result.success:
                logger.warning("Restarting setup hotspot failed: %s", result.message)
            return "retry_failed"

        # Weder Uplink noch Hotspot.
        self.hotspot_since = None
        if not interfaces:
            return "no_wifi"
        if detect.get("access_point_support") == "unsupported":
            return "no_ap"

        reference = max(self.started, self.last_uplink or 0.0)
        if now - reference < self.grace:
            return "waiting"

        logger.info("No network for %ss; starting setup hotspot on %s", int(now - reference), interfaces[0])
        result = service.start_fallback_hotspot(interfaces[0])
        if result.success:
            self.hotspot_since = self._clock()
            return "hotspot_started"
        logger.warning("Starting setup hotspot failed: %s", result.message)
        return "hotspot_failed"

    # ------------------------------------------------------------------

    def run_forever(self) -> None:
        logger.info(
            "Network watchdog active (grace=%ss, retry=%ss)", self.grace, self.retry_interval
        )
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:
                logger.exception("Network watchdog tick failed")
            self._stop.wait(self.poll_interval)

    def start(self) -> threading.Thread:
        thread = threading.Thread(target=self.run_forever, daemon=True, name="network-watchdog")
        thread.start()
        return thread

    def stop(self) -> None:
        self._stop.set()
