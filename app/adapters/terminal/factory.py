import platform

from .base import TerminalAdapter


def create_terminal_adapter() -> TerminalAdapter:
    if platform.system() != "Linux":
        raise RuntimeError("Diese Anwendung unterstützt nur Linux.")

    from .linux import LinuxTerminalAdapter

    return LinuxTerminalAdapter()
