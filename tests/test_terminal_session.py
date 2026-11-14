import os
import platform
import unittest


@unittest.skipUnless(
    platform.system() == "Linux",
    "Benötigt Linux und ein POSIX-Pseudoterminal.",
)
class TestTerminalSession(unittest.TestCase):
    def test_terminal_session(self):
        from app.adapters.terminal.factory import create_terminal_adapter
        from app.services.terminal_session import TerminalSession

        adapter = create_terminal_adapter()
        pid, fd = adapter.start("/bin/sh", None, [])
        session = TerminalSession(pid, fd)

        try:
            session.resize(80, 24)
            session.write("echo TERMINAL_SESSION_OK\n")
            import time
            output = ""
            for _ in range(50):
                time.sleep(0.05)
                try:
                    data = os.read(session.fd, 4096)
                    output += data.decode("utf-8", errors="replace")
                    if "TERMINAL_SESSION_OK" in output:
                        break
                except OSError:
                    break
            self.assertIn("TERMINAL_SESSION_OK", output)
        finally:
            session.close()

    def test_window_size_is_set_before_program_starts(self):
        # Die Autodarts-TUI bleibt mit 0x0 gelegentlich beim Start hängen:
        # Die Größe muss schon gelten, wenn das Programm startet.
        from app.adapters.terminal.factory import create_terminal_adapter
        from app.services.terminal_session import TerminalSession

        adapter = create_terminal_adapter()
        pid, fd = adapter.start("/bin/sh", None, ["-c", "stty size"], cols=97, rows=31)
        session = TerminalSession(pid, fd)
        try:
            import time
            output = ""
            for _ in range(50):
                time.sleep(0.05)
                try:
                    output += os.read(session.fd, 4096).decode("utf-8", errors="replace")
                except OSError:
                    break
                if "31 97" in output:
                    break
            self.assertIn("31 97", output)
        finally:
            session.close()


class FakeWebSocket:
    def __init__(self, messages, delay=0.0):
        self.messages = list(messages)
        self.delay = delay

    async def recv(self):
        import asyncio
        if self.delay:
            await asyncio.sleep(self.delay)
        if not self.messages:
            await asyncio.sleep(3600)
        return self.messages.pop(0)


@unittest.skipUnless(
    platform.system() == "Linux",
    "Benötigt Linux und ein POSIX-Pseudoterminal.",
)
class TestHangingTuiIsRestarted(unittest.TestCase):
    def test_restarts_tui_without_output(self):
        # "autodarts remote" hängt gelegentlich beim Start ohne jede Ausgabe.
        import asyncio
        from unittest.mock import patch

        from app.adapters.terminal.factory import create_terminal_adapter
        from app.services import terminal_server

        adapter = create_terminal_adapter()
        scripts = iter([
            "sleep 30",  # hängt: keine Ausgabe
            "printf 'HELLO_TUI_0123456789'; sleep 30",
        ])

        class FakeService:
            def start_tui(self, cols, rows):
                return adapter.start("/bin/sh", None, ["-c", next(scripts)], cols=cols, rows=rows)

        class RecordingWebSocket(FakeWebSocket):
            remote_address = ("test", 0)

            def __init__(self):
                super().__init__(["RESIZE:80:24"])
                self.sent = []

            async def send(self, text):
                self.sent.append(text)

            def __aiter__(self):
                return self

            async def __anext__(self):
                await asyncio.sleep(3600)

        async def scenario():
            ws = RecordingWebSocket()
            task = asyncio.create_task(terminal_server.terminal(ws))
            for _ in range(100):
                await asyncio.sleep(0.05)
                if "HELLO_TUI" in "".join(ws.sent):
                    break
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            return "".join(ws.sent)

        with patch.object(terminal_server, "TerminalService", FakeService), \
                patch.object(terminal_server, "FIRST_OUTPUT_TIMEOUT", 0.5):
            output = asyncio.run(scenario())

        self.assertIn("neuer Versuch", output)
        self.assertIn("HELLO_TUI", output)


class TestInitialTerminalSize(unittest.TestCase):
    def _run(self, ws, timeout=0.2):
        import asyncio
        from app.services.terminal_server import initial_size
        return asyncio.run(initial_size(ws, timeout=timeout))

    def test_uses_size_reported_by_browser(self):
        self.assertEqual(self._run(FakeWebSocket(["RESIZE:132:43"])), (132, 43, None))

    def test_falls_back_to_default_without_report(self):
        from app.adapters.terminal.base import DEFAULT_COLS, DEFAULT_ROWS
        self.assertEqual(self._run(FakeWebSocket([])), (DEFAULT_COLS, DEFAULT_ROWS, None))

    def test_keeps_early_keystrokes(self):
        from app.adapters.terminal.base import DEFAULT_COLS, DEFAULT_ROWS
        self.assertEqual(self._run(FakeWebSocket(["q"])), (DEFAULT_COLS, DEFAULT_ROWS, "q"))

    def test_rejects_invalid_sizes(self):
        from app.services.terminal_server import parse_resize
        self.assertIsNone(parse_resize("RESIZE:0:40"))
        self.assertIsNone(parse_resize("RESIZE:abc:40"))
        self.assertIsNone(parse_resize("hello"))
        self.assertEqual(parse_resize("RESIZE:5000:40"), (1000, 40))


if __name__ == "__main__":
    unittest.main()
