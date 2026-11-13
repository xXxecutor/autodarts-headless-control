from app.adapters.system.factory import create_system_adapter


def reboot_system() -> bool:
    adapter = create_system_adapter()
    return adapter.reboot()


def shutdown_system() -> bool:
    adapter = create_system_adapter()
    return adapter.shutdown()


def get_system_logs(target: str = "app", lines: int = 50) -> str:
    adapter = create_system_adapter()
    return adapter.get_logs(target=target, lines=lines)