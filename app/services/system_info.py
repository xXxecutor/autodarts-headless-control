import getpass
import os
import platform
import socket
import sys


def get_app_version() -> str | None:
    try:
        from importlib.metadata import PackageNotFoundError, version

        return version("autodarts-headless-control")
    except (ImportError, PackageNotFoundError):
        return None


def get_system_info() -> dict:
    hostname = socket.gethostname()

    # Ports aus derselben Konfiguration wie die Server lesen.
    http_port = int(os.environ.get("HEADLESS_HTTP_PORT", "80"))
    ws_port = int(os.environ.get("HEADLESS_WS_PORT", "8092"))

    # mDNS-Adresse: nur ein Namensvorschlag, keine Erreichbarkeitsgarantie.
    mdns_hostname = (
        hostname
        if hostname.endswith(".local")
        else f"{hostname}.local"
    )

    return {
        "os": platform.system(),
        "os_version": platform.version(),
        "architecture": platform.machine(),
        "hostname": hostname,
        "mdns_hostname": mdns_hostname,
        "http_port": http_port,
        "ws_port": ws_port,
        "username": getpass.getuser(),
        "home": os.path.expanduser("~"),
        "python_version": platform.python_version(),
        "python_executable": sys.executable,
        "version": get_app_version(),
        "auto_update": os.environ.get("HEADLESS_AUTO_UPDATE", "1") != "0",
    }
