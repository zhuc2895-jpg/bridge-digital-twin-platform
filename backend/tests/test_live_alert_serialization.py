import json

from app.dependencies import create_services
from app.live_contract import build_sensor_update
from app.live_stream import SensorUpdatePublisher
from app.ws.message_contract import encode_message
from tests.factories import reading


class CapturingManager:
    def __init__(self):
        self.payloads = []

    def enqueue_broadcast(self, payload, *, queued_at=None):
        self.payloads.append(payload)


def test_malformed_alert_value_does_not_suppress_live_update(caplog):
    services = create_services()
    services.engine.submit_alert(
        sensor_id="S01",
        sensor_name="AI detector",
        level="yellow",
        message="Malformed AI value",
        value="not-a-number",
        threshold=300.0,
        source="ai_feature_arbitration",
        timestamp=1_700_000_000.0,
        details={},
    )
    manager = CapturingManager()
    publisher = SensorUpdatePublisher(services.engine, manager)

    publisher.publish([reading()])

    assert len(manager.payloads) == 1
    assert manager.payloads[0]["alerts"]
    assert any("sensor_update" in record.message for record in caplog.records)


def test_non_finite_alert_value_produces_standard_json():
    services = create_services()
    services.engine.submit_alert(
        sensor_id="S01",
        sensor_name="AI detector",
        level="yellow",
        message="Non-finite AI value",
        value=float("nan"),
        threshold=300.0,
        source="ai_feature_arbitration",
        timestamp=1_700_000_000.0,
        details={},
    )

    message = encode_message(build_sensor_update(services.engine, [reading()]))

    assert "NaN" not in message
    json.loads(
        message,
        parse_constant=lambda value: (_ for _ in ()).throw(
            ValueError(f"non-standard JSON constant: {value}")
        ),
    )
