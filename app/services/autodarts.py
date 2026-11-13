from app.adapters.autodarts.factory import create_autodarts_adapter


def get_autodarts_status() -> dict:
    adapter = create_autodarts_adapter()
    return adapter.status()


def start_autodarts() -> bool:
    adapter = create_autodarts_adapter()
    return adapter.start()


def restart_autodarts() -> bool:
    adapter = create_autodarts_adapter()
    return adapter.restart()

def ensure_autodarts_autostart(force: bool = False) -> dict:
    """Set up the Autodarts user service (autostart) without the TUI."""
    adapter = create_autodarts_adapter()
    return adapter.ensure_autostart(force=force)
