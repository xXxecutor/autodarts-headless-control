import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.updates import DISABLED_FLAG, auto_update_status, set_auto_update


class TestAutoUpdateSwitch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = patch.dict(os.environ, {"HEADLESS_STATE_DIR": self.tmp.name, "HEADLESS_AUTO_UPDATE": "1"})
        env.start()
        self.addCleanup(env.stop)
        self.flag = Path(self.tmp.name) / DISABLED_FLAG

    def test_enabled_by_default(self):
        self.assertEqual(auto_update_status(), {"enabled": True, "locked": False})

    def test_disable_creates_flag_and_enable_removes_it(self):
        result = set_auto_update(False)
        self.assertTrue(result["ok"])
        self.assertFalse(result["enabled"])
        self.assertTrue(self.flag.exists())

        result = set_auto_update(True)
        self.assertTrue(result["ok"])
        self.assertTrue(result["enabled"])
        self.assertFalse(self.flag.exists())

    def test_enable_twice_is_harmless(self):
        self.assertTrue(set_auto_update(True)["ok"])
        self.assertTrue(set_auto_update(True)["ok"])

    def test_env_file_locks_switch(self):
        with patch.dict(os.environ, {"HEADLESS_AUTO_UPDATE": "0"}):
            self.assertEqual(auto_update_status(), {"enabled": False, "locked": True})
            result = set_auto_update(True)
            self.assertFalse(result["ok"])
            self.assertEqual(result["error"], "locked")
            self.assertFalse(self.flag.exists())

    def test_update_units_honour_flag(self):
        # Beide Update-Dienste müssen dieselbe Markierungsdatei beachten.
        root = Path(__file__).resolve().parents[1] / "packaging" / "systemd"
        for unit in ("autodarts-headless-control-update.service", "autodarts-update.service"):
            text = (root / unit).read_text(encoding="utf-8")
            self.assertIn(f"ConditionPathExists=!/var/lib/autodarts-headless-control/{DISABLED_FLAG}", text, unit)


class TestAutoUpdateEndpoint(unittest.TestCase):
    def _post(self, payload):
        from app.main import RequestHandler

        body = json.dumps(payload).encode()

        class TestHandler(RequestHandler):
            def __init__(self):
                self.path = "/api/system/auto-update"
                self.command = "POST"
                self.headers = {"Content-Length": str(len(body))}
                self.client_address = ("10.0.0.5", 1234)
                self.rfile = io.BytesIO(body)
                self.wfile = io.BytesIO()
                self.status = None

            def send_response(self, status, message=None):
                self.status = status

            def send_header(self, name, value):
                pass

            def end_headers(self):
                pass

        handler = TestHandler()
        handler.do_POST()
        return handler

    @patch("app.main.set_auto_update", return_value={"enabled": False, "locked": False, "ok": True})
    def test_switch_off(self, mock_set):
        handler = self._post({"enabled": False})
        self.assertEqual(handler.status, 200)
        mock_set.assert_called_once_with(False)

    def test_rejects_non_boolean(self):
        handler = self._post({"enabled": "nein"})
        self.assertEqual(handler.status, 400)

    @patch("app.main.set_auto_update", return_value={"enabled": False, "locked": True, "ok": False, "error": "locked"})
    def test_locked_returns_conflict(self, _set):
        self.assertEqual(self._post({"enabled": True}).status, 409)


if __name__ == "__main__":
    unittest.main()
