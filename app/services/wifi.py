from app.adapters.wifi.factory import create_wifi_adapter


def get_wifi_capabilities() -> dict:
    """Return detected networking capabilities without changing the system."""
    adapter = create_wifi_adapter()
    return adapter.detect()
