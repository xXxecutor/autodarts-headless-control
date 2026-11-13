import logging
import re
import subprocess
import threading
import time
from typing import Any, Callable

logger = logging.getLogger(__name__)

from .base import (
    ConnectionResult,
    HotspotConfig,
    WifiManagerAdapter,
    WifiNetwork,
)


HOTSPOT_PREFIX = "autodarts-hotspot-"
# nmcli liefert im Terse-Modus je nach Befehl Kurz- oder Langnamen.
UPLINK_TYPES = {"ethernet", "802-3-ethernet", "wifi", "802-11-wireless"}
WIFI_TYPES = {"wifi", "802-11-wireless"}
ACTIVATION_WAIT_SECONDS = 45


class NetworkManagerBackend(WifiManagerAdapter):
    """NetworkManager (nmcli) backend for Wi-Fi management."""

    def __init__(self, sudo_prefix: list[str] | None = None):
        """
        Args:
            sudo_prefix: Command prefix for privileged operations, e.g. ["sudo", "-n"]
                         or ["pkexec"] if polkit is configured. None = no prefix (assumes root).
        """
        self._sudo = sudo_prefix or []
        self._nmcli = self._find_nmcli()

    def _find_nmcli(self) -> str | None:
        import shutil
        return shutil.which("nmcli")

    def is_available(self) -> bool:
        return self._nmcli is not None

    @property
    def backend_name(self) -> str:
        return "NetworkManager"

    def _run(
        self,
        args: list[str],
        check: bool = False,
        sudo: bool = False,
        timeout: int = 30,
    ) -> subprocess.CompletedProcess:
        cmd = (self._sudo if sudo else []) + [self._nmcli] + args
        try:
            return subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=check,
            )
        except subprocess.TimeoutExpired:
            # Ein hängendes nmcli darf weder Request-Handler noch
            # Hintergrund-Threads mit einer Exception beenden.
            logger.warning("nmcli timed out after %ss: %s", timeout, args[:3])
            return subprocess.CompletedProcess(cmd, 124, "", f"nmcli timed out after {timeout}s")

    def _activate(self, connection_name: str) -> subprocess.CompletedProcess:
        """Activate a profile and wait for the result (e.g. wrong PSK)."""
        return self._run(
            ["--wait", str(ACTIVATION_WAIT_SECONDS), "connection", "up", connection_name],
            sudo=True,
            timeout=ACTIVATION_WAIT_SECONDS + 15,
        )

    @staticmethod
    def _split_terse(line: str) -> list[str]:
        """Split nmcli terse output on unescaped colons and unescape fields."""
        fields = re.split(r"(?<!\\):", line)
        return [f.replace("\\:", ":").replace("\\\\", "\\") for f in fields]

    def has_uplink(self, active: list[dict[str, Any]] | None = None) -> bool:
        """True if a regular (non-hotspot) Ethernet or Wi-Fi connection is up."""
        if active is None:
            active = self.get_active_connections()
        return any(
            c.get("state") == "activated"
            and c.get("type") in UPLINK_TYPES
            and not c.get("name", "").startswith(HOTSPOT_PREFIX)
            for c in active
        )

    def connect_known(self, interface: str) -> bool:
        """Let NetworkManager pick and activate the best saved profile."""
        if not self.is_available():
            return False
        self._run(["device", "wifi", "rescan", "ifname", interface], sudo=True)
        res = self._run(
            ["--wait", str(ACTIVATION_WAIT_SECONDS), "device", "connect", interface],
            sudo=True,
            timeout=ACTIVATION_WAIT_SECONDS + 15,
        )
        return res.returncode == 0

    def scan_networks(self, interface: str, rescan: bool = True) -> list[WifiNetwork]:
        """Scan for Wi-Fi networks using nmcli.

        rescan=False only lists NetworkManager's cached results, which avoids
        disturbing the active Wi-Fi link or hotspot on frequent status polls.
        """
        if not self.is_available():
            return []

        if rescan:
            self._run(["device", "wifi", "rescan", "ifname", interface], sudo=True)

        result = self._run([
            "-t",  # tab-separated
            "-f", "SSID,SIGNAL,SECURITY,FREQ,IN-USE",
            "device", "wifi", "list", "ifname", interface
        ])

        by_ssid: dict[str, WifiNetwork] = {}
        if result.returncode == 0:
            for line in result.stdout.strip().splitlines():
                if not line:
                    continue
                parts = self._split_terse(line)
                if len(parts) < 5:
                    continue
                ssid = parts[0]
                if not ssid:
                    continue  # versteckte Netzwerke ohne SSID
                try:
                    signal = int(parts[1]) if parts[1] else 0
                except ValueError:
                    signal = 0
                security = parts[2] if parts[2] and parts[2] != "--" else "open"
                try:
                    freq = int(parts[3].split()[0]) if parts[3] else 0
                except ValueError:
                    freq = 0
                in_use = parts[4].strip() == "*"

                network = WifiNetwork(
                    ssid=ssid,
                    signal=signal,
                    security=security,
                    frequency=freq,
                    in_use=in_use,
                )
                # Mehrere BSSIDs (Mesh, 2.4/5 GHz) zu einem Eintrag zusammenfassen.
                existing = by_ssid.get(ssid)
                if existing is None:
                    by_ssid[ssid] = network
                elif network.signal > existing.signal:
                    network.in_use = network.in_use or existing.in_use
                    by_ssid[ssid] = network
                else:
                    existing.in_use = existing.in_use or network.in_use
        return list(by_ssid.values())

    def connect(
        self,
        interface: str,
        ssid: str,
        password: str,
        connection_name: str | None = None,
        deferred_activation: bool = False,
        on_result: Callable[[ConnectionResult], None] | None = None,
        recovery_hotspot: HotspotConfig | None = None,
    ) -> ConnectionResult:
        """Create and activate a Wi-Fi connection profile.

        on_result is called from the background thread with the final outcome
        of a deferred activation; recovery_hotspot is restarted if it fails.
        """
        if not self.is_available():
            return ConnectionResult(False, "NetworkManager not available")

        if not connection_name:
            connection_name = f"autodarts-{ssid}"

        # Delete existing connection with same name if exists
        self._run(["connection", "delete", connection_name], sudo=True)

        # Create new connection
        args = [
            "connection", "add",
            "type", "wifi",
            "con-name", connection_name,
            "ifname", interface,
            # Argumente gehen ohne Shell an nmcli: SSID unverändert übergeben.
            "ssid", ssid,
        ]

        if password:
            args += ["wifi-sec.key-mgmt", "wpa-psk", "wifi-sec.psk", password]
        else:
            args += ["wifi-sec.key-mgmt", "none"]

        result = self._run(args, sudo=True)

        if result.returncode != 0:
            return ConnectionResult(False, f"Failed to create connection: {result.stderr.strip()}")

        if deferred_activation:
            def _bg_activate():
                try:
                    time.sleep(1.0)
                    logger.info("Deferred activation: bringing up connection %s on %s", connection_name, interface)
                    res = self._activate(connection_name)
                    if res.returncode == 0:
                        logger.info("Deferred activation succeeded for %s", connection_name)
                        if on_result:
                            on_result(ConnectionResult(True, f"Verbunden mit '{ssid}'.", connection_name))
                        return

                    error = (res.stderr or res.stdout or "").strip()
                    logger.warning("Deferred activation failed for %s: %s", connection_name, error)
                    # Fehlerhaftes Profil (z. B. falsches Passwort) nicht behalten,
                    # sonst versucht NetworkManager es bei jedem Boot erneut.
                    self._run(["connection", "delete", connection_name], sudo=True)
                    if on_result:
                        on_result(ConnectionResult(
                            False,
                            f"Verbindung mit '{ssid}' fehlgeschlagen. Bitte Passwort und Empfang prüfen.",
                            connection_name,
                        ))

                    if not self.has_uplink():
                        logger.warning("No active network remaining. Restarting recovery hotspot...")
                        self.start_hotspot(
                            interface,
                            recovery_hotspot or HotspotConfig(ssid="Autodarts-Setup", password="autodarts123"),
                        )
                except Exception:
                    logger.exception("Deferred activation crashed for %s", connection_name)

            threading.Thread(target=_bg_activate, daemon=True).start()
            return ConnectionResult(
                True,
                f"WLAN-Profil für '{ssid}' gespeichert. Verbindung wird in Kürze hergestellt. Der Einrichtungs-Hotspot wird beendet.",
                connection_name,
            )

        # Immediate activation (default/synchronous)
        result = self._activate(connection_name)

        if result.returncode != 0:
            # Cleanup on failure
            self._run(["connection", "delete", connection_name], sudo=True)
            return ConnectionResult(False, f"Failed to activate connection: {result.stderr.strip()}")

        return ConnectionResult(True, "Connected successfully", connection_name)

    def disconnect(self, interface: str, connection_name: str) -> ConnectionResult:
        """Disconnect a connection (but keep profile)."""
        if not self.is_available():
            return ConnectionResult(False, "NetworkManager not available")

        result = self._run(["connection", "down", connection_name], sudo=True)

        if result.returncode != 0:
            return ConnectionResult(False, f"Failed to disconnect: {result.stderr.strip()}")

        return ConnectionResult(True, "Disconnected", connection_name)

    def start_hotspot(self, interface: str, config: HotspotConfig, deferred: bool = False) -> ConnectionResult:
        """Start a Wi-Fi hotspot using NetworkManager's built-in AP mode."""
        if not self.is_available():
            return ConnectionResult(False, "NetworkManager not available")

        connection_name = f"autodarts-hotspot-{config.ssid}"

        # Delete existing hotspot connection if exists
        self._run(["connection", "delete", connection_name], sudo=True)

        # Parse subnet for gateway IP
        # config.subnet format: "192.168.4.1/24"
        gateway_ip = config.subnet.split("/")[0]

        args = [
            "connection", "add",
            "type", "wifi",
            "con-name", connection_name,
            "ifname", interface,
            "wifi.mode", "ap",
            "wifi.ssid", config.ssid,
            "wifi.band", "bg",  # 2.4 GHz
            "wifi.channel", str(config.channel),
            "wifi-sec.key-mgmt", "wpa-psk",
            "wifi-sec.psk", config.password,
            "ipv4.method", "shared",  # NM handles DHCP + NAT
            "ipv4.addresses", f"{gateway_ip}/24",
            "connection.autoconnect", "no",
        ]

        result = self._run(args, sudo=True)

        if result.returncode != 0:
            return ConnectionResult(False, f"Failed to create hotspot: {result.stderr.strip()}")

        if deferred:
            def _bg_start():
                try:
                    time.sleep(1.0)
                    logger.info("Deferred start: activating hotspot %s on %s", connection_name, interface)
                    res = self._activate(connection_name)
                    if res.returncode != 0:
                        logger.warning("Deferred hotspot activation failed: %s", res.stderr.strip())
                except Exception:
                    logger.exception("Deferred hotspot start crashed")

            threading.Thread(target=_bg_start, daemon=True).start()
            return ConnectionResult(True, f"Hotspot '{config.ssid}' wird gestartet.", connection_name)

        # Immediate activation (default/sync)
        result = self._activate(connection_name)

        if result.returncode != 0:
            self._run(["connection", "delete", connection_name], sudo=True)
            return ConnectionResult(False, f"Failed to start hotspot: {result.stderr.strip()}")

        return ConnectionResult(True, "Hotspot started", connection_name)

    def stop_hotspot(self, interface: str, connection_name: str, deferred: bool = False) -> ConnectionResult:
        """Stop hotspot and delete connection profile."""
        if not self.is_available():
            return ConnectionResult(False, "NetworkManager not available")

        if deferred:
            def _bg_stop():
                try:
                    time.sleep(1.0)
                    logger.info("Deferred stop: bringing down hotspot %s on %s", connection_name, interface)
                    self._run(["connection", "down", connection_name], sudo=True)
                    self._run(["connection", "delete", connection_name], sudo=True)
                except Exception:
                    logger.exception("Deferred hotspot stop crashed")

            threading.Thread(target=_bg_stop, daemon=True).start()
            return ConnectionResult(True, "Hotspot wird beendet.", connection_name)

        # Immediate stop (default/sync)
        result = self._run(["connection", "down", connection_name], sudo=True)

        if result.returncode != 0:
            return ConnectionResult(False, f"Failed to stop hotspot: {result.stderr.strip()}")

        # Delete connection profile
        result = self._run(["connection", "delete", connection_name], sudo=True)

        if result.returncode != 0:
            return ConnectionResult(False, f"Failed to delete hotspot profile: {result.stderr.strip()}")

        return ConnectionResult(True, "Hotspot stopped", connection_name)

    def get_active_connections(self) -> list[dict[str, Any]]:
        """List active connections."""
        if not self.is_available():
            return []

        result = self._run([
            "-t", "-f", "NAME,TYPE,DEVICE,STATE",
            "connection", "show", "--active"
        ])

        connections = []
        if result.returncode == 0:
            for line in result.stdout.strip().splitlines():
                if not line:
                    continue
                parts = self._split_terse(line)
                if len(parts) >= 4:
                    connections.append({
                        "name": parts[0],
                        "type": parts[1],
                        "device": parts[2],
                        "state": parts[3],
                    })
        return connections

    def get_saved_connections(self) -> list[dict[str, Any]]:
        """List all saved connections (active and inactive)."""
        if not self.is_available():
            return []

        result = self._run([
            "-t", "-f", "NAME,TYPE,DEVICE",
            "connection", "show"
        ])

        connections = []
        if result.returncode == 0:
            for line in result.stdout.strip().splitlines():
                if not line:
                    continue
                parts = self._split_terse(line)
                if len(parts) >= 2:
                    connections.append({
                        "name": parts[0],
                        "type": parts[1],
                        "device": parts[2] if len(parts) > 2 else "",
                    })
        return connections

    def delete_connection(self, connection_name: str) -> ConnectionResult:
        """Delete a saved connection profile (for handover/reset)."""
        if not self.is_available():
            return ConnectionResult(False, "NetworkManager not available")

        # Only delete if it's an autodarts-managed connection
        if not (connection_name.startswith("autodarts-") or connection_name.startswith("autodarts-hotspot-")):
            return ConnectionResult(False, f"Refusing to delete non-autodarts connection: {connection_name}")

        result = self._run(["connection", "delete", connection_name], sudo=True)

        if result.returncode != 0:
            return ConnectionResult(False, f"Failed to delete connection: {result.stderr.strip()}")

        return ConnectionResult(True, "Connection deleted", connection_name)