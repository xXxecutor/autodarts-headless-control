import threading
import unittest
from unittest.mock import MagicMock, patch

from app.adapters.wifi_manager import ConnectionResult
from app.services.network_watchdog import NetworkWatchdog


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


HOTSPOT = {"name": "autodarts-hotspot-Autodarts-Setup", "type": "802-11-wireless", "device": "wlan0", "state": "activated"}
WIFI = {"name": "autodarts-Home", "type": "802-11-wireless", "device": "wlan0", "state": "activated"}


class TestNetworkWatchdog(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.manager = MagicMock()
        self.manager.is_available.return_value = True
        self.active = []
        self.manager.get_active_connections.side_effect = lambda: list(self.active)
        self.manager.has_uplink.side_effect = lambda active=None: any(
            c is not HOTSPOT for c in (self.active if active is None else active)
        )

        self.service = MagicMock()
        self.service.lock = threading.RLock()
        self.service.is_busy.return_value = False
        self.service._get_manager.return_value = self.manager
        self.service.refresh_detection.return_value = {"access_point_support": "unknown"}
        self.service.wireless_interfaces.return_value = ["wlan0"]
        self.service.find_hotspot.side_effect = lambda active: next(
            (c for c in active if c["name"].startswith("autodarts-hotspot-")), None
        )
        self.service.has_saved_wifi_profiles.return_value = True

        def _start(iface):
            self.active = [HOTSPOT]
            return ConnectionResult(True, "Hotspot started", HOTSPOT["name"])

        self.service.start_fallback_hotspot.side_effect = _start

        self.watchdog = NetworkWatchdog(self.service, grace=45, retry_interval=300, clock=self.clock)
        clients = patch.object(NetworkWatchdog, "_hotspot_has_clients", return_value=False)
        self.mock_clients = clients.start()
        self.addCleanup(clients.stop)

    def test_waits_for_grace_period_after_boot(self):
        self.assertEqual(self.watchdog.tick(), "waiting")
        self.clock.advance(30)
        self.assertEqual(self.watchdog.tick(), "waiting")
        self.service.start_fallback_hotspot.assert_not_called()

    def test_starts_hotspot_after_grace_without_network(self):
        self.clock.advance(46)
        self.assertEqual(self.watchdog.tick(), "hotspot_started")
        self.service.start_fallback_hotspot.assert_called_once_with("wlan0")

    def test_no_hotspot_while_online(self):
        self.active = [WIFI]
        self.clock.advance(500)
        self.assertEqual(self.watchdog.tick(), "online")
        self.service.start_fallback_hotspot.assert_not_called()

    def test_grace_restarts_after_connection_loss(self):
        self.active = [WIFI]
        self.clock.advance(500)
        self.watchdog.tick()
        self.active = []
        self.clock.advance(20)
        self.assertEqual(self.watchdog.tick(), "waiting")
        self.clock.advance(30)
        self.assertEqual(self.watchdog.tick(), "hotspot_started")

    def test_does_nothing_while_user_connect_is_pending(self):
        self.service.is_busy.return_value = True
        self.clock.advance(500)
        self.assertEqual(self.watchdog.tick(), "busy")
        self.service.start_fallback_hotspot.assert_not_called()

    def test_no_hotspot_when_ap_unsupported(self):
        self.service.refresh_detection.return_value = {"access_point_support": "unsupported"}
        self.clock.advance(500)
        self.assertEqual(self.watchdog.tick(), "no_ap")

    def test_idle_hotspot_retries_known_wifi_and_reconnects(self):
        self.clock.advance(46)
        self.watchdog.tick()  # hotspot started
        self.clock.advance(299)
        self.assertEqual(self.watchdog.tick(), "hotspot")

        def _connect_known(iface):
            self.active = [WIFI]
            return True

        self.manager.connect_known.side_effect = _connect_known
        self.clock.advance(2)
        self.assertEqual(self.watchdog.tick(), "reconnected")
        self.manager.stop_hotspot.assert_called_once_with("wlan0", HOTSPOT["name"])

    def test_failed_retry_restarts_hotspot(self):
        self.clock.advance(46)
        self.watchdog.tick()
        self.active = [HOTSPOT]
        self.manager.stop_hotspot.side_effect = lambda *a, **k: setattr(self, "active", [])
        self.manager.connect_known.return_value = False
        self.clock.advance(301)
        self.assertEqual(self.watchdog.tick(), "retry_failed")
        self.assertEqual(self.service.start_fallback_hotspot.call_count, 2)

    def test_hotspot_with_clients_is_not_interrupted(self):
        self.clock.advance(46)
        self.watchdog.tick()
        self.mock_clients.return_value = True
        for _ in range(10):
            self.clock.advance(60)
            self.assertEqual(self.watchdog.tick(), "hotspot")
        self.manager.stop_hotspot.assert_not_called()

    def test_http_activity_counts_as_client(self):
        self.clock.advance(46)
        self.watchdog.tick()
        self.clock.advance(290)
        self.watchdog.note_client_activity()
        self.clock.advance(20)
        self.assertEqual(self.watchdog.tick(), "hotspot")

    def test_hotspot_stays_without_saved_profiles(self):
        self.service.has_saved_wifi_profiles.return_value = False
        self.clock.advance(46)
        self.watchdog.tick()
        self.clock.advance(1000)
        self.assertEqual(self.watchdog.tick(), "hotspot")
        self.manager.stop_hotspot.assert_not_called()


if __name__ == "__main__":
    unittest.main()
