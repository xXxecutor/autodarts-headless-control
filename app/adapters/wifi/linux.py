import platform
import shutil
import subprocess
from pathlib import Path
from .base import WifiAdapter


class LinuxWifiAdapter(WifiAdapter):
    NET_ROOT = Path("/sys/class/net")
    TOOLS = ("nmcli", "iw", "ip", "rfkill", "hostapd", "dnsmasq")

    def detect_wireless_interfaces(self) -> dict:
        """Inspect visible network interfaces without changing the system."""

        if platform.system() != "Linux":
            return {
                "supported_platform": False,
                "interfaces": [],
                "wireless_visible": False,
            }

        net_root = self.NET_ROOT
        try:
            interfaces = []
            for device in net_root.iterdir():
                if (
                    (device / "wireless").is_dir()
                    or (device / "phy80211").exists()
                ):
                    interfaces.append(device.name)

            return {
                "supported_platform": True,
                "interfaces": sorted(interfaces),
                "wireless_visible": bool(interfaces),
            }
        except OSError:
            return {
                "supported_platform": True,
                "interfaces": [],
                "wireless_visible": None,
            }

    def detect_access_point_support(self, interfaces: list[str], iw_path: str | None) -> str:
        """Return supported, unsupported or unknown without changing Wi-Fi."""
        import subprocess

        if not interfaces or not iw_path:
            return "unknown"

        try:
            result = subprocess.run(
                [iw_path, "list"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return "unknown"

        if result.returncode != 0:
            return "unknown"

        output = result.stdout
        if "Supported interface modes:" not in output:
            return "unknown"

        section = output.split("Supported interface modes:", 1)[1]
        section = section.split("\nBand ", 1)[0]

        if any(
            line.strip() == "* AP"
            for line in section.splitlines()
        ):
            return "supported"

        return "unsupported"

    def detect_network_status(self, ip_path: str | None) -> dict:
        """Inspect network links and IP addresses without changing them."""
        if not ip_path:
            return {
                "available": False,
                "interfaces": [],
                "connected": None,
            }

        try:
            links_result = subprocess.run(
                [ip_path, "-brief", "link", "show"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            addresses_result = subprocess.run(
                [ip_path, "-brief", "address", "show"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return {
                "available": False,
                "interfaces": [],
                "connected": None,
            }

        if links_result.returncode != 0 or addresses_result.returncode != 0:
            return {
                "available": False,
                "interfaces": [],
                "connected": None,
            }

        addresses = {}
        for line in addresses_result.stdout.splitlines():
            parts = line.split()
            if parts:
                addresses[parts[0]] = [
                    value for value in parts[2:]
                    if "/" in value
                ]

        interfaces = []
        for line in links_result.stdout.splitlines():
            parts = line.split()
            if len(parts) < 2:
                continue

            name, state = parts[0], parts[1]
            if name == "lo":
                continue

            interfaces.append({
                "name": name,
                "state": state,
                "addresses": addresses.get(name, []),
            })

        connected = any(
            item["state"] == "UP" and item["addresses"]
            for item in interfaces
        )

        return {
            "available": True,
            "interfaces": interfaces,
            "connected": connected,
        }

    def detect(self) -> dict:
        if platform.system() != "Linux":
            return {
                "supported_platform": False,
                "tools": {},
                "network_manager": None,
                "wireless": {
                    "interfaces": [],
                    "wireless_visible": False,
                },
                "access_point_support": "unknown",
            }

        tools = {
            name: shutil.which(name)
            for name in self.TOOLS
        }

        network_manager = (
            "NetworkManager" if tools["nmcli"] else None
        )

        wireless = self.detect_wireless_interfaces()
        network_status = self.detect_network_status(tools["ip"])

        # Erst später mit einer gezielten iw-Abfrage verifizieren.
        # Ein sichtbares WLAN-Interface allein genügt nicht.
        access_point_support = self.detect_access_point_support(
            wireless["interfaces"],
            tools["iw"],
        )

        return {
            "supported_platform": True,
            "tools": tools,
            "network_manager": network_manager,
            "wireless": wireless,
            "access_point_support": access_point_support,
            "network_status": network_status,
        }