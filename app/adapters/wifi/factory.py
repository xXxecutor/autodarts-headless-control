import platform

from .base import WifiAdapter
from .linux import LinuxWifiAdapter


def create_wifi_adapter() -> WifiAdapter:
    if platform.system() != "Linux":
        raise RuntimeError("Diese Anwendung unterstützt nur Linux.")

    return LinuxWifiAdapter()
