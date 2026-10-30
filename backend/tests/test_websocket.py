from fastapi.testclient import TestClient

from app.dependencies import create_services
from app.main import create_app
from tests.factories import reading


class OneShotSimulator:
    is_running = False

    def next_readings(self, timestamp=None):
        self.is_running = False
        return [reading(timestamp=timestamp or 1_700_000_000.0)]


def test_websocket_stats_expose_retained_alert_count():
    services = create_services()
    services.simulator = OneShotSimulator()
    app = create_app(services)

    with TestClient(app) as client:
        with client.websocket_connect("/ws/live") as websocket:
            payload = websocket.receive_json()

    assert payload["type"] == "sensor_update"
    assert payload["stats"]["retained_alerts"] == 0
    assert "recent_alerts" not in payload["stats"]
    assert "active_alerts" not in payload["stats"]