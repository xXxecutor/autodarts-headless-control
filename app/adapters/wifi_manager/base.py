from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class WifiNetwork:
    """Represents a discovered Wi-Fi network."""
    ssid: str
    signal: int  # dBm or percentage
    security: str  # WPA2, WPA3, open, etc.
    frequency: int  # MHz
    in_use: bool = False


@dataclass
class ConnectionResult:
    """Result of a connection attempt."""
    success: bool
    message: str
    connection_name: str | None = None


@dataclass
class HotspotConfig:
    """Configuration for AP/hotspot mode."""
    ssid: str
    password: str  # WPA2-PSK, 8-63 chars
    channel: int = 6  # 2.4 GHz channel 1-11
    subnet: str = "192.168.4.1/24"  # gateway IP/CIDR
    dhcp_start: str = "192.168.4.10"
    dhcp_end: str = "192.168.4.100"


class WifiManagerAdapter(ABC):
    """Abstract base for Wi-Fi management backends (write operations)."""

    @abstractmethod
    def scan_networks(self, interface: str, rescan: bool = True) -> list[WifiNetwork]:
        """Scan for available Wi-Fi networks (rescan=False: cached list only)."""
        raise NotImplementedError

    @abstractmethod
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
        """Connect to a Wi-Fi network, creating a persistent connection profile."""
        raise NotImplementedError

    @abstractmethod
    def disconnect(self, interface: str, connection_name: str) -> ConnectionResult:
        """Disconnect and optionally delete a connection profile."""
        raise NotImplementedError

    @abstractmethod
    def start_hotspot(self, interface: str, config: HotspotConfig, deferred: bool = False) -> ConnectionResult:
        """Start an access point (hotspot) on the given interface."""
        raise NotImplementedError

    @abstractmethod
    def stop_hotspot(self, interface: str, connection_name: str, deferred: bool = False) -> ConnectionResult:
        """Stop the access point and clean up."""
        raise NotImplementedError

    @abstractmethod
    def get_active_connections(self) -> list[dict[str, Any]]:
        """List currently active connection profiles."""
        raise NotImplementedError

    @abstractmethod
    def get_saved_connections(self) -> list[dict[str, Any]]:
        """List all saved connection profiles (active and inactive)."""
        raise NotImplementedError

    @abstractmethod
    def delete_connection(self, connection_name: str) -> ConnectionResult:
        """Delete a saved connection profile (for handover/reset)."""
        raise NotImplementedError

    @abstractmethod
    def has_uplink(self, active: list[dict[str, Any]] | None = None) -> bool:
        """True if a regular (non-hotspot) Ethernet/Wi-Fi connection is active."""
        raise NotImplementedError

    @abstractmethod
    def connect_known(self, interface: str) -> bool:
        """Ask the backend to activate the best saved Wi-Fi profile."""
        raise NotImplementedError

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this backend is available on the current system."""
        raise NotImplementedError

    @property
    @abstractmethod
    def backend_name(self) -> str:
        """Human-readable backend name for logging/debugging."""
        raise NotImplementedError