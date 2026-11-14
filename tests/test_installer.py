import re
import unittest
from pathlib import Path

INSTALLER = Path(__file__).resolve().parents[1] / "installer" / "install.sh"


class TestInstallScript(unittest.TestCase):
    def test_os_release_does_not_override_version(self):
        # /etc/os-release definiert VERSION (z. B. "13 (trixie)"). Direkt
        # eingelesen ueberschreibt es die Release-Version des Installers und
        # macht die Download-URL kaputt.
        for line in INSTALLER.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if re.match(r"^(\.|source)\s+/etc/os-release\b", stripped):
                self.fail(f"os-release wird direkt eingelesen: {line!r}")


if __name__ == "__main__":
    unittest.main()
