import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.adapters.autodarts import linux as ad_linux
from app.adapters.autodarts.linux import LinuxAutodartsAdapter


class TestAutodartsAutostart(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.exe = self.home / ".local" / "share" / "autodarts" / "autodarts"
        self.exe.parent.mkdir(parents=True)
        self.exe.write_text("#!/bin/sh\n")

        self.adapter = LinuxAutodartsAdapter()
        patches = [
            patch.object(LinuxAutodartsAdapter, "_find_path", return_value=str(self.exe)),
            patch.object(LinuxAutodartsAdapter, "_service_home", return_value=self.home),
            patch.object(LinuxAutodartsAdapter, "_owned_by_current_user", return_value=True),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

        self.calls = []

        def fake_run(cmd, **kwargs):
            self.calls.append(cmd)
            if "is-enabled" in cmd:
                return MagicMock(returncode=0, stdout="enabled\n", stderr="")
            if "is-active" in cmd:
                return MagicMock(returncode=0, stdout="active\n", stderr="")
            return MagicMock(returncode=0, stdout="", stderr="")

        run_patch = patch("app.adapters.autodarts.linux.subprocess.run", side_effect=fake_run)
        run_patch.start()
        self.addCleanup(run_patch.stop)

    def tearDown(self):
        self.tmp.cleanup()

    @property
    def unit(self):
        return self.home / ".config" / "systemd" / "user" / "autodarts.service"

    def test_creates_and_enables_user_service(self):
        result = self.adapter.ensure_autostart()

        self.assertTrue(result["ok"])
        self.assertTrue(result["changed"])
        content = self.unit.read_text()
        self.assertIn(f"ExecStart={self.exe} run", content)
        self.assertIn("WantedBy=default.target", content)
        self.assertIn(["systemctl", "--user", "enable", "--now", "autodarts.service"], self.calls)

    def test_prefers_stable_local_bin_symlink(self):
        link = self.home / ".local" / "bin" / "autodarts"
        link.parent.mkdir(parents=True)
        link.write_text("")  # existiert = wird verwendet
        self.adapter.ensure_autostart()
        self.assertIn(f"ExecStart={link} run", self.unit.read_text())

    def test_does_not_overwrite_unit_created_by_tui(self):
        self.unit.parent.mkdir(parents=True)
        self.unit.write_text("# from TUI\n")
        result = self.adapter.ensure_autostart()
        self.assertTrue(result["ok"])
        self.assertEqual(self.unit.read_text(), "# from TUI\n")

    def test_runs_only_once_unless_forced(self):
        self.adapter.ensure_autostart()
        self.unit.unlink()  # Nutzer hat "Run as a service" in der TUI abgewählt
        self.calls.clear()

        result = self.adapter.ensure_autostart()
        self.assertEqual(result["reason"], "already_handled")
        self.assertFalse(self.unit.exists())

        result = self.adapter.ensure_autostart(force=True)
        self.assertTrue(result["changed"])
        self.assertTrue(self.unit.exists())

    def test_falls_back_to_wants_symlink_without_user_manager(self):
        def failing_enable(cmd, **kwargs):
            if "enable" in cmd:
                return MagicMock(returncode=1, stdout="", stderr="Failed to connect to bus")
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch("app.adapters.autodarts.linux.subprocess.run", side_effect=failing_enable), \
                patch.object(Path, "symlink_to") as mock_symlink:
            result = self.adapter.ensure_autostart()

        self.assertTrue(result["ok"])
        mock_symlink.assert_called_once_with(self.unit)

    def test_not_installed(self):
        with patch.object(LinuxAutodartsAdapter, "_find_path", return_value=None):
            result = self.adapter.ensure_autostart()
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "not_installed")

    def test_foreign_owner_is_left_alone(self):
        with patch.object(LinuxAutodartsAdapter, "_owned_by_current_user", return_value=False):
            result = self.adapter.ensure_autostart()
        self.assertEqual(result["reason"], "different_user")
        self.assertFalse(self.unit.exists())

    def test_board_manager_reachable(self):
        with patch("app.adapters.autodarts.linux.socket.create_connection") as conn:
            self.assertTrue(self.adapter.board_manager_reachable())
            conn.assert_called_once_with(("127.0.0.1", ad_linux.BOARD_MANAGER_PORT), timeout=1.0)
        with patch("app.adapters.autodarts.linux.socket.create_connection", side_effect=OSError):
            self.assertFalse(self.adapter.board_manager_reachable())


if __name__ == "__main__":
    unittest.main()
