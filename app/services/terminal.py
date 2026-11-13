from dataclasses import dataclass

from app.adapters.autodarts.factory import create_autodarts_adapter
from app.adapters.terminal.factory import create_terminal_adapter


@dataclass
class TerminalLaunchInfo:
    executable: str
    user: str | None
    arguments: list[str]


class TerminalService:
    def __init__(self):
        self.autodarts = create_autodarts_adapter()
        self.terminal = create_terminal_adapter()

    def get_tui_launch_info(self):
        info = self.autodarts.terminal_launch_info()

        if not info:
            return None

        return TerminalLaunchInfo(
            executable=info["executable"],
            user=info["user"],
            # "remote -H localhost" verbindet zum laufenden Board (pi user auf Port 3180)
            # und öffnet die interaktive TUI
            arguments=["remote", "-H", "localhost"],
        )

    def start_tui(self):
        launch_info = self.get_tui_launch_info()

        if not launch_info:
            return None

        return self.terminal.start(
            launch_info.executable,
            launch_info.user,
            launch_info.arguments,
        )

    def is_autodarts_running(self):
        return self.autodarts.is_running()