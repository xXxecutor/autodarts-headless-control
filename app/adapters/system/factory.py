import platform

from .base import SystemAdapter
from .linux import LinuxSystemAdapter


def create_system_adapter() -> SystemAdapter:
    if platform.system() != "Linux":
        raise RuntimeError("Diese Anwendung unterstützt nur Linux.")

    return LinuxSystemAdapter()
