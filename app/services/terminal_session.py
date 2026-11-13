import asyncio
import codecs
import fcntl
import os
import signal
import struct
import termios
import time


class TerminalSession:
    def __init__(self, pid: int, fd: int):
        self.pid = pid
        self.fd = fd
        # TUIs nutzen Rahmen-/Sonderzeichen (mehrbytig in UTF-8). Ein inkrementeller
        # Decoder verhindert kaputte Zeichen, wenn ein Zeichen über zwei read()-Blöcke geht.
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._closed = False

    def resize(self, cols: int, rows: int):
        cols = max(1, min(int(cols), 1000))
        rows = max(1, min(int(rows), 1000))
        winsize = struct.pack("HHHH", rows, cols, 0, 0)
        fcntl.ioctl(self.fd, termios.TIOCSWINSZ, winsize)

    async def read(self):
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(None, os.read, self.fd, 4096)
        except OSError:
            # EIO: Kindprozess hat das PTY geschlossen.
            return b""

    def decode(self, data: bytes) -> str:
        return self._decoder.decode(data)

    def write(self, data: str):
        os.write(self.fd, data.encode("utf-8"))

    def _reap(self, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while True:
            try:
                pid, _ = os.waitpid(self.pid, os.WNOHANG)
            except ChildProcessError:
                return True
            if pid != 0:
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.05)

    def close(self):
        if self._closed:
            return
        self._closed = True

        # Erst den Prozess beenden (das entblockt auch einen laufenden read()),
        # dann einsammeln, damit keine Zombie-Prozesse zurückbleiben.
        for sig, wait in ((signal.SIGHUP, 1.0), (signal.SIGTERM, 1.0), (signal.SIGKILL, 1.0)):
            try:
                os.kill(self.pid, sig)
            except ProcessLookupError:
                break
            except PermissionError:
                # z. B. via sudo als anderer Benutzer gestartet: Schließen des
                # PTY sendet SIGHUP an die Session.
                break
            if self._reap(wait):
                break

        try:
            os.close(self.fd)
        except OSError:
            pass

        if not self._reap(1.0):
            # Notfalls im Hintergrund blockierend einsammeln.
            def _wait():
                try:
                    os.waitpid(self.pid, 0)
                except ChildProcessError:
                    pass

            import threading
            threading.Thread(target=_wait, daemon=True).start()
