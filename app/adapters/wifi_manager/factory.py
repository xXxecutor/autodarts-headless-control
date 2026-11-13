from typing import Any

from .base import WifiManagerAdapter
from .networkmanager import NetworkManagerBackend


def create_wifi_manager(
    preferred_backend: str | None = None,
    sudo_prefix: list[str] | None = None,
    detect_result: dict[str, Any] | None = None,
) -> WifiManagerAdapter:
    """
    Create a Wi-Fi manager backend instance.

    NetworkManager is the required backend for Autodarts Headless Control.

    Args:
        preferred_backend: Optional backend name ("networkmanager").
        sudo_prefix: Command prefix for privileged operations (e.g. ["sudo", "-n"]).
        detect_result: Output from WifiAdapter.detect() for auto-detection hints.

    Returns:
        WifiManagerAdapter instance using NetworkManager.
    """
    return NetworkManagerBackend(sudo_prefix)