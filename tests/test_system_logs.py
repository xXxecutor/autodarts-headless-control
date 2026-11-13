import unittest
from unittest.mock import patch, MagicMock
from app.adapters.system.linux import LinuxSystemAdapter
from app.services.system import get_system_logs


class TestSystemLogs(unittest.TestCase):

    @patch("subprocess.run")
    def test_get_logs_app_target(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="Line 1\nLine 2\n", stderr="")
        adapter = LinuxSystemAdapter()
        logs = adapter.get_logs(target="app", lines=50)

        mock_run.assert_called_once_with(
            ["journalctl", "-n", "50", "--no-pager", "-u", "autodarts-headless-control"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        self.assertIn("Line 1", logs)

    @patch("subprocess.run")
    def test_get_logs_firewall_target(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="FW sync\n", stderr="")
        adapter = LinuxSystemAdapter()
        logs = adapter.get_logs(target="firewall", lines=30)

        mock_run.assert_called_once_with(
            ["journalctl", "-n", "30", "--no-pager", "-t", "autodarts-firewall-sync", "-t", "autodarts-dispatcher"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        self.assertIn("FW sync", logs)

    @patch("subprocess.run")
    def test_get_logs_autodarts_target(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="Autodarts Board Log\n", stderr="")
        adapter = LinuxSystemAdapter()
        logs = adapter.get_logs(target="autodarts", lines=40)

        mock_run.assert_called_once_with(
            ["journalctl", "-n", "40", "--no-pager", "_SYSTEMD_USER_UNIT=autodarts.service", "+", "_SYSTEMD_UNIT=autodarts-update.service"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        self.assertIn("Autodarts Board Log", logs)

    @patch("subprocess.run")
    def test_get_logs_lines_clamping(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="OK", stderr="")
        adapter = LinuxSystemAdapter()

        # lines < 10 -> 10
        adapter.get_logs(lines=2)
        self.assertEqual(mock_run.call_args[0][0][2], "10")

        # lines > 200 -> 200
        adapter.get_logs(lines=500)
        self.assertEqual(mock_run.call_args[0][0][2], "200")

    @patch("subprocess.run")
    def test_get_logs_error_handling(self, mock_run):
        mock_run.side_effect = OSError("command not found")
        adapter = LinuxSystemAdapter()
        logs = adapter.get_logs()
        self.assertIn("Fehler beim Abrufen der Protokolle", logs)

    @patch("app.services.system.create_system_adapter")
    def test_service_delegates_to_adapter(self, mock_factory):
        mock_adapter = MagicMock()
        mock_adapter.get_logs.return_value = "Service Log"
        mock_factory.return_value = mock_adapter

        result = get_system_logs("firewall", 25)
        mock_adapter.get_logs.assert_called_once_with(target="firewall", lines=25)
        self.assertEqual(result, "Service Log")


if __name__ == "__main__":
    unittest.main()
