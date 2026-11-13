from enum import Enum
from typing import Any


class NetworkDecision(Enum):
    """Result of network policy decision."""

    KEEP_ETHERNET = "keep_ethernet"
    CONNECT_WIFI = "connect_wifi"
    START_HOTSPOT = "start_hotspot"
    ERROR_NO_NETWORK = "error_no_network"


def _is_ethernet_interface(name: str) -> bool:
    """Check if interface name indicates Ethernet."""
    return name.startswith(("eth", "eno", "enp", "enx", "ens"))


def _is_wireless_interface(name: str) -> bool:
    """Check if interface name indicates wireless."""
    return name.startswith(("wl", "wlan", "wifi"))


def _has_active_ip(interface: dict[str, Any]) -> bool:
    """Check if interface has an IP address assigned."""
    return bool(interface.get("addresses"))


def _is_interface_up(interface: dict[str, Any]) -> bool:
    """Check if interface link state is UP."""
    return interface.get("state") == "UP"


def decide_network_action(detect_result: dict[str, Any]) -> NetworkDecision:
    """
    Decide network action based on detection results.

    Priority order:
    1. Active Ethernet with IP -> KEEP_ETHERNET (never disconnect)
    2. Active Wireless with IP -> CONNECT_WIFI (known WiFi reachable)
    3. AP mode supported -> START_HOTSPOT (fallback)
    4. Otherwise -> ERROR_NO_NETWORK

    Args:
        detect_result: Output from WifiAdapter.detect()

    Returns:
        NetworkDecision enum value
    """
    # Guard: unsupported platform
    if not detect_result.get("supported_platform", False):
        return NetworkDecision.ERROR_NO_NETWORK

    network_status = detect_result.get("network_status", {})
    if not network_status.get("available", False):
        # No network status available, check if we can at least start a hotspot
        ap_support = detect_result.get("access_point_support", "unknown")
        if ap_support == "supported":
            return NetworkDecision.START_HOTSPOT
        return NetworkDecision.ERROR_NO_NETWORK

    interfaces = network_status.get("interfaces", [])

    # 1. Check for active Ethernet with IP (highest priority, never disconnect)
    for iface in interfaces:
        if _is_ethernet_interface(iface["name"]) and _is_interface_up(iface) and _has_active_ip(iface):
            return NetworkDecision.KEEP_ETHERNET

    # 2. Check for active Wireless with IP (known WiFi connected)
    for iface in interfaces:
        if _is_wireless_interface(iface["name"]) and _is_interface_up(iface) and _has_active_ip(iface):
            return NetworkDecision.CONNECT_WIFI

    # 3. No active connection with IP - check if we can start a hotspot
    ap_support = detect_result.get("access_point_support", "unknown")
    if ap_support == "supported":
        return NetworkDecision.START_HOTSPOT

    # 4. Wireless interface exists but no IP and no AP support
    wireless = detect_result.get("wireless", {})
    if wireless.get("wireless_visible") and wireless.get("interfaces"):
        # Wireless hardware exists but not connected and can't do AP
        return NetworkDecision.ERROR_NO_NETWORK

    # 5. No wireless hardware visible at all
    return NetworkDecision.ERROR_NO_NETWORK