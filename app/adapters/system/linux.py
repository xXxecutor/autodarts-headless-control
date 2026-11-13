import logging
import subprocess

logger = logging.getLogger(__name__)

from .base import SystemAdapter


class LinuxSystemAdapter(SystemAdapter):

    def reboot(self) -> bool:
        for cmd in [["systemctl", "reboot", "-i"], ["sudo", "-n", "/usr/sbin/reboot"], ["/usr/sbin/reboot"]]:
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
                if result.returncode == 0:
                    logger.info("Reboot succeeded with command: %s", cmd)
                    return True
                logger.warning("Reboot command %s failed (code %s): %s", cmd, result.returncode, result.stderr.strip())
            except (OSError, subprocess.SubprocessError) as exc:
                logger.warning("Reboot command %s raised error: %s", cmd, exc)
                continue
        return False

    def shutdown(self) -> bool:
        for cmd in [["systemctl", "poweroff", "-i"], ["sudo", "-n", "/usr/sbin/poweroff"], ["/usr/sbin/poweroff"]]:
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
                if result.returncode == 0:
                    logger.info("Shutdown succeeded with command: %s", cmd)
                    return True
                logger.warning("Shutdown command %s failed (code %s): %s", cmd, result.returncode, result.stderr.strip())
            except (OSError, subprocess.SubprocessError) as exc:
                logger.warning("Shutdown command %s raised error: %s", cmd, exc)
                continue
        return False

    def get_logs(self, target: str = "app", lines: int = 50) -> str:
        try:
            safe_lines = min(max(int(lines), 10), 200)
        except (ValueError, TypeError):
            safe_lines = 50

        cmd = ["journalctl", "-n", str(safe_lines), "--no-pager"]
        if target == "app":
            cmd.extend(["-u", "autodarts-headless-control"])
        elif target == "firewall":
            cmd.extend(["-t", "autodarts-firewall-sync", "-t", "autodarts-dispatcher"])
        elif target == "autodarts":
            cmd.extend(["_SYSTEMD_USER_UNIT=autodarts.service", "+", "_SYSTEMD_UNIT=autodarts-update.service"])
        else:
            cmd.extend(["-p", "4"])  # warnings/errors

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            return result.stdout if result.returncode == 0 else result.stderr
        except (OSError, subprocess.SubprocessError) as err:
            return f"Fehler beim Abrufen der Protokolle: {err}"