"""Automatische Updates ein-/ausschalten (Headless Control und Autodarts).

Der Webdienst läuft ohne Root-Rechte und darf nur in sein Datenverzeichnis
schreiben. Der Schalter ist deshalb eine Markierungsdatei dort; beide
Update-Units (autodarts-headless-control-update.service und
autodarts-update.service) laufen nur, wenn sie fehlt
(ConditionPathExists=!…).

HEADLESS_AUTO_UPDATE=0 in /etc/autodarts-headless-control.env hat Vorrang:
Dann sind die Updates von Headless Control fest abgeschaltet und der
Schalter in der Weboberfläche ist gesperrt.
"""

import os
from pathlib import Path

DISABLED_FLAG = "auto-update-disabled"


def _state_dir() -> Path:
    return Path(os.environ.get("HEADLESS_STATE_DIR", "/var/lib/autodarts-headless-control"))


def _flag_path() -> Path:
    return _state_dir() / DISABLED_FLAG


def _locked() -> bool:
    return os.environ.get("HEADLESS_AUTO_UPDATE", "1").strip().strip('"') == "0"


def auto_update_status() -> dict:
    locked = _locked()
    return {
        "enabled": not locked and not _flag_path().exists(),
        "locked": locked,
    }


def set_auto_update(enabled: bool) -> dict:
    """Schaltet die automatischen Updates; Rückgabe wie auto_update_status() plus ok/error."""
    if _locked():
        return {**auto_update_status(), "ok": False, "error": "locked"}

    flag = _flag_path()
    try:
        if enabled:
            flag.unlink(missing_ok=True)
        else:
            flag.parent.mkdir(parents=True, exist_ok=True)
            flag.write_text("Automatische Updates in der Weboberfläche abgeschaltet.\n", encoding="utf-8")
    except OSError as exc:
        return {**auto_update_status(), "ok": False, "error": str(exc)}

    return {**auto_update_status(), "ok": True}
