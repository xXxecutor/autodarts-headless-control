import os
try:
    import pwd
except ImportError:
    pwd = None
import shutil
import socket
import subprocess
from pathlib import Path

from .base import AutodartsAdapter


UNIT_NAME = "autodarts.service"
BOARD_MANAGER_PORT = int(os.environ.get("AUTODARTS_BOARD_MANAGER_PORT", "3180"))


class LinuxAutodartsAdapter(AutodartsAdapter):
    def _find_path(self) -> str | None:
        candidates = []

        # 1. Service-User 'autodarts' Installation (Installer default) BEVOR aktuellen User
        # /var/lib/autodarts-headless-control ist das Home-Verzeichnis des Service-Users
        service_user_home = Path("/var/lib/autodarts-headless-control")
        candidates.extend([
            service_user_home / ".local" / "bin" / "autodarts",
            service_user_home / ".local" / "share" / "autodarts" / "autodarts",
        ])

        # 2. Standard PATH lookup
        found = shutil.which("autodarts")
        if found:
            candidates.append(found)

        # 3. Home-Verzeichnis des aktuellen Benutzers
        home = Path.home()
        candidates.extend([
            home / ".local" / "bin" / "autodarts",
            home / ".local" / "share" / "autodarts" / "autodarts",
        ])

        # 4. Falls die Anwendung als anderer Benutzer läuft:
        # mögliche Home-Verzeichnisse aus /etc/passwd prüfen.
        try:
            for entry in pwd.getpwall():
                user_home = Path(entry.pw_dir)
                candidates.extend([
                    user_home / ".local" / "bin" / "autodarts",
                    user_home / ".local" / "share" / "autodarts" / "autodarts",
                ])
        except (OSError, ImportError):
            pass

        checked = set()

        for candidate in candidates:
            try:
                path = Path(candidate).resolve()
                if path in checked:
                    continue
                checked.add(path)

                if path.is_file() and os.access(path, os.X_OK):
                    return str(path)
            except OSError:
                continue

        return None

    def status(self) -> dict:
        path = self._find_path()
        installed = path is not None
        return {
            "installed": installed,
            "running": self.is_running() if installed else False,
            "path": path,
            "version": self.version() if installed else None,
            "terminal_user": self.terminal_user() if installed else None,
            "service": self.service_state() if installed else None,
            "board_manager_port": BOARD_MANAGER_PORT,
            "board_manager_reachable": self.board_manager_reachable() if installed else False,
        }

    # ------------------------------------------------------------------
    # systemd-User-Dienst (Autostart ohne TUI)
    # ------------------------------------------------------------------

    def _user_env(self, user: str | None = None) -> dict:
        """Environment that lets "systemctl --user" reach the user manager.

        Der systemd-Dienst setzt kein XDG_RUNTIME_DIR; ohne diese Variable
        findet "systemctl --user" den User-Bus von Autodarts nicht.
        """
        env = os.environ.copy()
        try:
            uid = pwd.getpwnam(user).pw_uid if user else os.getuid()
            runtime_dir = f"/run/user/{uid}"
            if uid == os.getuid() and os.path.isdir(runtime_dir):
                env.setdefault("XDG_RUNTIME_DIR", runtime_dir)
                env.setdefault("DBUS_SESSION_BUS_ADDRESS", f"unix:path={runtime_dir}/bus")
        except (KeyError, OSError, AttributeError):
            pass
        return env

    def _systemctl_user(self, *args: str, timeout: int = 15) -> subprocess.CompletedProcess | None:
        try:
            return subprocess.run(
                ["systemctl", "--user", *args],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                env=self._user_env(),
            )
        except (OSError, subprocess.SubprocessError):
            return None

    def _run_systemctl_user(self, action: str, timeout: int = 15) -> bool:
        user = self.terminal_user()
        candidates = []
        if user:
            candidates.append(["systemctl", f"--machine={user}@.host", "--user", action, UNIT_NAME])
            candidates.append(["sudo", "-n", "systemctl", f"--machine={user}@.host", "--user", action, UNIT_NAME])
        candidates.append(["systemctl", "--user", action, UNIT_NAME])

        env = self._user_env(user)
        for cmd in candidates:
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    check=False,
                    env=env,
                )
                if result.returncode == 0:
                    return True
            except (OSError, subprocess.SubprocessError):
                continue
        return False

    @staticmethod
    def _service_home() -> Path:
        try:
            return Path(pwd.getpwuid(os.getuid()).pw_dir)
        except (KeyError, AttributeError):
            return Path.home()

    def _unit_path(self) -> Path:
        return self._service_home() / ".config" / "systemd" / "user" / UNIT_NAME

    def _marker_path(self) -> Path:
        return self._service_home() / ".config" / "autodarts-headless-control" / "autostart-installed"

    def _owned_by_current_user(self, path: str) -> bool:
        try:
            return os.stat(path).st_uid == os.getuid()
        except (OSError, AttributeError):
            return False

    def service_state(self) -> dict:
        """Report whether the Autodarts user service exists, is enabled and active."""
        unit_installed = self._unit_path().is_file()
        enabled = self._systemctl_user("is-enabled", UNIT_NAME, timeout=5)
        active = self._systemctl_user("is-active", UNIT_NAME, timeout=5)
        return {
            "unit_installed": unit_installed,
            "enabled": (enabled.stdout.strip() if enabled else "") or "unknown",
            "active": (active.stdout.strip() if active else "") or "unknown",
        }

    def _unit_content(self, executable: str) -> str:
        # Der Symlink in ~/.local/bin bleibt bei Updates gleich (autodarts.sh tauscht nur das Ziel).
        link = self._service_home() / ".local" / "bin" / "autodarts"
        exe = str(link) if link.exists() else executable
        return (
            "# Angelegt von Autodarts Headless Control.\n"
            "# Entspricht \"Run as a service\" im Service-Bereich der Autodarts-TUI.\n"
            "[Unit]\n"
            "Description=Autodarts board (headless)\n"
            "\n"
            "[Service]\n"
            "Type=simple\n"
            f"ExecStart={exe} run\n"
            "Restart=on-failure\n"
            "RestartSec=5\n"
            "\n"
            "[Install]\n"
            "WantedBy=default.target\n"
        )

    def ensure_autostart(self, force: bool = False) -> dict:
        """Install and enable the Autodarts user service without the TUI.

        Läuft automatisch einmal pro Gerät (Markierungsdatei). Danach wird eine
        bewusste Entscheidung in der TUI ("Run as a service" abgewählt) respektiert;
        force=True (Button in der Weboberfläche) richtet den Autostart erneut ein.
        """
        path = self._find_path()
        if not path:
            return {"ok": False, "changed": False, "reason": "not_installed"}
        if not self._owned_by_current_user(path):
            # Autodarts gehört einem anderen Benutzer (z. B. Entwicklungsrechner):
            # dessen systemd-User-Instanz können wir nicht verwalten.
            return {"ok": False, "changed": False, "reason": "different_user"}

        marker = self._marker_path()
        if marker.exists() and not force:
            return {"ok": True, "changed": False, "reason": "already_handled", "service": self.service_state()}

        unit = self._unit_path()
        changed = False
        try:
            if not unit.exists():
                unit.parent.mkdir(parents=True, exist_ok=True)
                unit.write_text(self._unit_content(path), encoding="utf-8")
                changed = True

            self._systemctl_user("daemon-reload")
            enabled = self._systemctl_user("enable", "--now", UNIT_NAME, timeout=30)
            if enabled is None or enabled.returncode != 0:
                # User-Manager (noch) nicht erreichbar: Dienst trotzdem für den
                # nächsten Boot aktivieren (genau das macht "systemctl enable").
                wants = unit.parent / "default.target.wants"
                wants.mkdir(parents=True, exist_ok=True)
                link = wants / UNIT_NAME
                if not link.exists():
                    link.symlink_to(unit)
                    changed = True

            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text("1\n", encoding="utf-8")
        except OSError as exc:
            return {"ok": False, "changed": changed, "reason": f"write_failed: {exc}"}

        return {"ok": True, "changed": changed, "reason": "installed", "service": self.service_state()}

    def board_manager_reachable(self, timeout: float = 1.0) -> bool:
        """True if the Autodarts Board Manager (web UI, v2.1+) answers on its port."""
        try:
            with socket.create_connection(("127.0.0.1", BOARD_MANAGER_PORT), timeout=timeout):
                return True
        except OSError:
            return False

    def start(self) -> bool:
        if not self._find_path():
            return False
        if self.is_running():
            return True
        return self._run_systemctl_user("start", timeout=10)

    def restart(self) -> bool:
        if not self._find_path():
            return False
        return self._run_systemctl_user("restart", timeout=20)

    def version(self) -> str | None:
        path = self._find_path()
        if not path:
            return None
        try:
            result = subprocess.run(
                [path, "--version"],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
            output = (result.stdout or result.stderr).strip()
            return output or None
        except (OSError, subprocess.SubprocessError):
            return None

    def is_running(self) -> bool:
        path = self._find_path()
        if not path:
            return False
        try:
            for entry in os.listdir("/proc"):
                if not entry.isdigit():
                    continue
                # Try reading exe symlink
                try:
                    executable = os.readlink(
                        os.path.join("/proc", entry, "exe")
                    )
                    if os.path.realpath(executable) == path or Path(executable).name == "autodarts":
                        return True
                except OSError:
                    pass

                # If exe symlink was unreadable (e.g. PermissionError across users),
                # inspect /proc/<pid>/comm which is world-readable
                try:
                    comm_file = os.path.join("/proc", entry, "comm")
                    if os.path.isfile(comm_file):
                        with open(comm_file, "r", encoding="utf-8", errors="replace") as f:
                            if f.read().strip() == "autodarts":
                                return True
                except OSError:
                    continue
            return False
        except OSError:
            return False

    def terminal_user(self) -> str | None:
        path = self._find_path()
        if not path:
            return None
        try:
            return pwd.getpwuid(os.stat(path).st_uid).pw_name
        except (OSError, KeyError):
            return None

    def terminal_launch_info(self):
        path = self._find_path()
        if not path:
            return None
        return {
            "executable": path,
            "user": self.terminal_user(),
            "arguments": [],
        }