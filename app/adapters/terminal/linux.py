import fcntl
import os
import pwd
import pty
import shutil
import signal
import struct
import termios

from .base import DEFAULT_COLS, DEFAULT_ROWS, TerminalAdapter


class LinuxTerminalAdapter(TerminalAdapter):

    def start(
        self,
        executable: str,
        user: str | None,
        arguments: list[str],
        cols: int = DEFAULT_COLS,
        rows: int = DEFAULT_ROWS,
    ):
        # Alles vor dem fork() vorbereiten: Der Server hat mehrere Threads, im
        # Kindprozess sind bis zum exec nur noch einfache Systemaufrufe sicher.
        cols = max(1, min(int(cols), 1000))
        rows = max(1, min(int(rows), 1000))
        winsize = struct.pack("HHHH", rows, cols, 0, 0)

        env = dict(os.environ)
        env.setdefault("TERM", "xterm-256color")
        current_user = pwd.getpwuid(os.getuid()).pw_name
        if user and user != current_user:
            program = shutil.which("sudo") or "/usr/bin/sudo"
            argv = [program, "-u", user, executable, *arguments]
        else:
            program = executable
            argv = [executable, *arguments]

        pid, fd = pty.fork()

        if pid == 0:
            # Kindprozess: darf unter keinen Umständen in den Python-Code des
            # Servers zurückkehren, sonst liefe eine zweite Server-Instanz im PTY.
            try:
                # Fenstergröße setzen, BEVOR die TUI startet. Mit 0x0 bleibt die
                # Autodarts-TUI gelegentlich beim Start hängen.
                fcntl.ioctl(0, termios.TIOCSWINSZ, winsize)
            except OSError:
                pass
            # Wie subprocess (restore_signals): Python ignoriert SIGPIPE und
            # SIGXFSZ, das würde sonst an das gestartete Programm vererbt.
            for sig in (signal.SIGPIPE, signal.SIGXFSZ):
                try:
                    signal.signal(sig, signal.SIG_DFL)
                except (OSError, ValueError):
                    pass
            try:
                os.execve(program, argv, env)
            except BaseException as exc:  # noqa: BLE001 - child must always exit
                try:
                    os.write(2, f"\r\nAutodarts-Terminal konnte nicht gestartet werden: {exc}\r\n".encode())
                finally:
                    os._exit(127)

        return pid, fd
