import logging
import threading
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

from app.adapters.wifi.factory import create_wifi_adapter
from app.adapters.wifi_manager import (
    ConnectionResult,
    HotspotConfig,
    WifiNetwork,
    create_wifi_manager,
)
from app.services.network_policy import NetworkDecision, decide_network_action


HOTSPOT_PREFIX = "autodarts-hotspot-"
DEFAULT_HOTSPOT = HotspotConfig(ssid="Autodarts-Setup", password="autodarts123")
WIFI_TYPES = {"wifi", "802-11-wireless"}

# Solange eine vom Nutzer angestoßene Verbindung aufgebaut wird,
# darf der Watchdog nicht dazwischenfunken (nmcli --wait 45 + Puffer).
CONNECT_GRACE_SECONDS = 90


@dataclass
class NetworkState:
    """Current network state for UI/status reporting."""
    decision: NetworkDecision
    detect_result: dict[str, Any]
    active_connections: list[dict[str, Any]]
    available_networks: list[WifiNetwork]
    hotspot_active: bool
    hotspot_config: HotspotConfig | None = None


class WifiManagerService:
    """
    High-level Wi-Fi management service.

    Coordinates:
    - NetworkPolicy (read-only decisions)
    - WifiManagerAdapter (write operations via NM or fallback)
    - Provides unified API for web UI, startup logic and the hotspot watchdog
    """

    def __init__(
        self,
        sudo_prefix: list[str] | None = None,
        preferred_backend: str | None = None,
    ):
        """
        Args:
            sudo_prefix: Command prefix for privileged ops (e.g. ["sudo", "-n"])
            preferred_backend: Optional backend override (default: "networkmanager")
        """
        self._sudo_prefix = sudo_prefix or []
        self._preferred_backend = preferred_backend
        self._wifi_adapter = create_wifi_adapter()
        self._wifi_manager = None  # Lazy init
        self._last_detect_result: dict[str, Any] | None = None

        # Serialisiert netzwerkverändernde Aktionen (UI-Requests und Watchdog).
        self.lock = threading.RLock()
        self._scan_cache: list[WifiNetwork] = []
        self._busy_until = 0.0
        self.last_connect_result: dict[str, Any] | None = None

    def _get_manager(self) -> Any:
        """Lazy initialization of wifi manager with current detection context."""
        if self._wifi_manager is None:
            self._wifi_manager = create_wifi_manager(
                preferred_backend=self._preferred_backend,
                sudo_prefix=self._sudo_prefix,
                detect_result=self._last_detect_result,
            )
        return self._wifi_manager

    def refresh_detection(self) -> dict[str, Any]:
        """Refresh network detection and cache result."""
        self._last_detect_result = self._wifi_adapter.detect()
        return self._last_detect_result

    # ------------------------------------------------------------------
    # Hilfsfunktionen für Watchdog und API
    # ------------------------------------------------------------------

    @staticmethod
    def find_hotspot(active: list[dict[str, Any]]) -> dict[str, Any] | None:
        for conn in active:
            if conn.get("name", "").startswith(HOTSPOT_PREFIX):
                return conn
        return None

    def wireless_interfaces(self, detect: dict[str, Any] | None = None) -> list[str]:
        detect = detect if detect is not None else self.refresh_detection()
        return list(detect.get("wireless", {}).get("interfaces", []) or [])

    def has_saved_wifi_profiles(self) -> bool:
        """True if a non-hotspot Wi-Fi profile exists that NM could auto-connect."""
        for conn in self._get_manager().get_saved_connections():
            if conn.get("type") in WIFI_TYPES and not conn.get("name", "").startswith(HOTSPOT_PREFIX):
                return True
        return False

    def mark_busy(self, seconds: float) -> None:
        """Suppress automatic watchdog actions for the given time."""
        self._busy_until = max(self._busy_until, time.monotonic() + seconds)

    def is_busy(self) -> bool:
        return time.monotonic() < self._busy_until

    def _visible_networks(self, networks: list[WifiNetwork]) -> list[WifiNetwork]:
        # Den eigenen Setup-Hotspot nicht als auswählbares Heimnetz anbieten.
        return [n for n in networks if n.ssid != DEFAULT_HOTSPOT.ssid]

    def scan(self, rescan: bool = True, active: list[dict[str, Any]] | None = None) -> list[WifiNetwork]:
        """Scan on all wireless interfaces, falling back to the last result.

        Viele WLAN-Chips (z. B. Raspberry Pi) können im AP-Modus nicht scannen.
        Damit die Einrichtungsseite im Hotspot trotzdem Netze zeigt, wird das
        letzte nicht-leere Ergebnis (vor Hotspot-Start erstellt) zurückgegeben.
        """
        manager = self._get_manager()
        networks: list[WifiNetwork] = []
        for iface in self.wireless_interfaces(self._last_detect_result or self.refresh_detection()):
            networks.extend(manager.scan_networks(iface, rescan=rescan))
        networks = self._visible_networks(networks)

        if networks:
            self._scan_cache = networks
            return networks

        if active is None:
            active = manager.get_active_connections()
        if self.find_hotspot(active) is not None:
            return list(self._scan_cache)
        return networks

    def get_network_state(self, rescan: bool = False) -> NetworkState:
        """Get complete current network state for UI.

        Status-Polling löst bewusst keinen aktiven Rescan aus, weil jeder
        Rescan die laufende WLAN-Verbindung bzw. den Hotspot kurz stört.
        """
        detect = self.refresh_detection()
        decision = decide_network_action(detect)
        manager = self._get_manager()

        active = manager.get_active_connections()
        hotspot = self.find_hotspot(active)
        networks = self.scan(rescan=rescan, active=active)

        return NetworkState(
            decision=decision,
            detect_result=detect,
            active_connections=active,
            available_networks=networks,
            hotspot_active=hotspot is not None,
            hotspot_config=None,
        )

    def execute_policy(self) -> ConnectionResult:
        """
        Execute the network policy decision.

        Called after handover; the continuous fallback logic lives in
        app.services.network_watchdog.
        """
        detect = self.refresh_detection()
        decision = decide_network_action(detect)
        manager = self._get_manager()

        wireless = detect.get("wireless", {})
        primary_wifi_iface = (wireless.get("interfaces") or [None])[0]

        if decision == NetworkDecision.KEEP_ETHERNET:
            # Ensure no hotspot is running on wifi iface
            if primary_wifi_iface:
                active = manager.get_active_connections()
                for conn in active:
                    if conn["name"].startswith(HOTSPOT_PREFIX) and conn["device"] == primary_wifi_iface:
                        manager.stop_hotspot(primary_wifi_iface, conn["name"])
            return ConnectionResult(True, "Ethernet active, no action needed")

        elif decision == NetworkDecision.CONNECT_WIFI:
            # NetworkManager handles auto-connect for saved profiles
            return ConnectionResult(True, "Known WiFi profile should auto-connect")

        elif decision == NetworkDecision.START_HOTSPOT:
            if not primary_wifi_iface:
                return ConnectionResult(False, "No wireless interface for hotspot")
            return self.start_fallback_hotspot(primary_wifi_iface)

        else:  # ERROR_NO_NETWORK
            return ConnectionResult(False, "No network available and hotspot not supported")

    def start_fallback_hotspot(self, interface: str) -> ConnectionResult:
        """Scan once (for the setup page) and start the setup hotspot."""
        with self.lock:
            try:
                self.scan(rescan=True, active=[])
            except Exception:
                logger.exception("Pre-hotspot scan failed")
            return self._get_manager().start_hotspot(interface, DEFAULT_HOTSPOT)

    def connect_to_wifi(
        self,
        ssid: str,
        password: str,
        interface: str | None = None,
        deferred_activation: bool | None = None,
    ) -> ConnectionResult:
        """Manually connect to a Wi-Fi network (called from UI)."""
        with self.lock:
            detect = self.refresh_detection()
            wireless = detect.get("wireless", {})
            interfaces = wireless.get("interfaces", [])

            if interface is None:
                interface = interfaces[0] if interfaces else None

            if not interface:
                return ConnectionResult(False, "No wireless interface available")

            manager = self._get_manager()

            # Auto-detect deferred_activation if not explicitly set:
            # If a hotspot is currently active, defer activation so the HTTP response
            # can reach the client before the hotspot teardown terminates the connection.
            if deferred_activation is None:
                deferred_activation = self.find_hotspot(manager.get_active_connections()) is not None

            self.mark_busy(CONNECT_GRACE_SECONDS)
            self.last_connect_result = {"ssid": ssid, "pending": True, "success": None, "message": ""}

            if deferred_activation:
                def _record(result: ConnectionResult) -> None:
                    self.last_connect_result = {
                        "ssid": ssid,
                        "pending": False,
                        "success": result.success,
                        "message": result.message,
                    }

                return manager.connect(
                    interface,
                    ssid,
                    password,
                    deferred_activation=True,
                    on_result=_record,
                    recovery_hotspot=DEFAULT_HOTSPOT,
                )

            result = manager.connect(interface, ssid, password)
            self.last_connect_result = {
                "ssid": ssid,
                "pending": False,
                "success": result.success,
                "message": result.message,
            }
            return result

    def start_hotspot_manual(
        self,
        config: HotspotConfig,
        interface: str | None = None,
        deferred: bool = False,
    ) -> ConnectionResult:
        """Manually start hotspot (called from UI/setup flow)."""
        with self.lock:
            detect = self.refresh_detection()
            wireless = detect.get("wireless", {})

            if interface is None:
                interface = (wireless.get("interfaces") or [None])[0]

            if not interface:
                return ConnectionResult(False, "No wireless interface available")

            # Netze vor dem Umschalten in den AP-Modus merken.
            try:
                self.scan(rescan=True, active=[])
            except Exception:
                logger.exception("Pre-hotspot scan failed")

            manager = self._get_manager()
            if deferred:
                return manager.start_hotspot(interface, config, deferred=True)
            return manager.start_hotspot(interface, config)

    def stop_hotspot(
        self,
        connection_name: str,
        interface: str,
        deferred: bool = False,
    ) -> ConnectionResult:
        """Stop hotspot (called after successful WiFi connect)."""
        with self.lock:
            manager = self._get_manager()
            # Manuell beendeter Hotspot: dem Watchdog Zeit für die Rückkehr ins WLAN geben.
            self.mark_busy(CONNECT_GRACE_SECONDS)
            if deferred:
                return manager.stop_hotspot(interface, connection_name, deferred=True)
            return manager.stop_hotspot(interface, connection_name)

    def prepare_handover(self, deferred: bool = False) -> ConnectionResult:
        """
        Prepare device for handover: delete all autodarts-managed Wi-Fi connections.
        Keeps Ethernet, system profiles, and Autodarts data intact.
        """
        self.refresh_detection()
        manager = self._get_manager()

        saved = manager.get_saved_connections()
        if not saved:
            saved = manager.get_active_connections()

        # Alle WLAN-Profile löschen, nicht nur die von Headless Control: Auf
        # dem Pi trägt z. B. der Raspberry Pi Imager das WLAN als
        # "netplan-wlan0-<SSID>" ein. LAN-, VPN- und andere Profile bleiben.
        def is_wifi_profile(conn) -> bool:
            return (
                conn.get("name", "").startswith("autodarts-")
                or conn.get("type", "") in ("wifi", "802-11-wireless")
            )

        to_delete = set()
        for conn in saved:
            if is_wifi_profile(conn):
                to_delete.add(conn["name"])

        # Also inspect active connections in case saved list missed anything
        for conn in manager.get_active_connections():
            if is_wifi_profile(conn):
                to_delete.add(conn["name"])

        if not to_delete:
            return ConnectionResult(True, "Es sind keine WLAN-Zugangsdaten gespeichert.")

        names = sorted(to_delete)

        if deferred:
            def _bg_handover():
                try:
                    time.sleep(1.0)
                    with self.lock:
                        logger.info("Deferred handover: deleting profiles %s", names)
                        for name in names:
                            manager.delete_connection(name)
                        self._scan_cache = []
                    time.sleep(2.0)
                    # If no Ethernet active, trigger policy to start setup hotspot
                    current_detect = self.refresh_detection()
                    if decide_network_action(current_detect) == NetworkDecision.START_HOTSPOT:
                        logger.info("Handover complete: starting recovery hotspot")
                        self.execute_policy()
                except Exception:
                    logger.exception("Deferred handover crashed")

            threading.Thread(target=_bg_handover, daemon=True).start()
            logger.info("Handover requested: %s", names)
            return ConnectionResult(
                True,
                "WLAN-Zugangsdaten werden gelöscht. Ohne LAN-Kabel startet gleich "
                "der Setup-Hotspot „Autodarts-Setup“."
            )

        deleted = []
        errors = []

        with self.lock:
            for name in names:
                result = manager.delete_connection(name)
                if result.success:
                    deleted.append(name)
                else:
                    errors.append(f"{name}: {result.message}")

        if errors:
            logger.warning("Handover incomplete: deleted %s, errors: %s", deleted, errors)
            return ConnectionResult(
                False,
                "Nicht alle WLAN-Zugangsdaten konnten gelöscht werden. "
                "Details stehen im Protokoll."
            )

        return ConnectionResult(True, "WLAN-Zugangsdaten gelöscht.")

    def get_backend_info(self) -> dict[str, Any]:
        """Get info about active backend for debugging."""
        manager = self._get_manager()
        return {
            "backend": manager.backend_name,
            "available": manager.is_available(),
            "sudo_prefix": self._sudo_prefix,
        }
