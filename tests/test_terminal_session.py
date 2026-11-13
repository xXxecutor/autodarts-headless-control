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


if __name__ == "__main__":
    unittest.main()
