import platform

from .base import AutodartsAdapter
from .linux import LinuxAutodartsAdapter


def create_autodarts_adapter() -> AutodartsAdapter:
    if platform.system() != "Linux":
        raise RuntimeError("Diese Anwendung unterstützt nur Linux.")

    return LinuxAutodartsAdapter()
