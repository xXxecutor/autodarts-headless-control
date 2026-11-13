import os
import pwd
import pty
import sys

from .base import TerminalAdapter


class LinuxTerminalAdapter(TerminalAdapter):

    def start(
        self,
        executable: str,
        user: str | None,
        arguments: list[str],
    ):
        pid, fd = pty.fork()

        if pid == 0:
            # Kindprozess: darf unter keinen Umständen in den Python-Code des
            # Servers zurückkehren, sonst liefe eine zweite Server-Instanz im PTY.
            try:
                os.environ.setdefault("TERM", "xterm-256color")
                current_user = pwd.getpwuid(os.getuid()).pw_name
                if user and user != current_user:
                    os.execvp("sudo", ["sudo", "-u", user, executable, *arguments])
                else:
                    os.execv(executable, [executable, *arguments])
            except BaseException as exc:  # noqa: BLE001 - child must always exit
                try:
                    sys.stderr.write(f"\r\nAutodarts-Terminal konnte nicht gestartet werden: {exc}\r\n")
                    sys.stderr.flush()
                finally:
                    os._exit(127)

        return pid, fd
