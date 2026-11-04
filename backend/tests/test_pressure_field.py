import json
import math
from collections.abc import Mapping
from typing import Any

from app.live_contract import (
    LiveFrameAssembler,
    LiveSensorSnapshot,
    MAX_SENSOR_UPDATE_BYTES,
)
from app.bridge_scene_profile import bundled_scene_profile
from app.pressure_field import build_pressure_update
from app.ws.message_contract import encode_message

from tests.factories import reading
from tests.helpers import OneShotSimulator, create_live_app


def _thresholds(sensor_id: str, sensor_type: str) -> dict[str, float]:
    del sensor_id
    return {
        "strain": {"yellow": 300.0, "orange": 450.0, "red": 600.0},
        "displacement": {"yellow": 30.0, "orange": 50.0, "red": 80.0},
        "acceleration": {"yellow": 2.0, "orange": 3.5, "red": 5.0},
        "temperature": {"yellow": 45.0, "orange": 55.0, "red": 65.0},
    }[sensor_type]


def _projected(sensor: dict, physical_state: str) -> dict:
    return {
        **sensor,
        "physical_state": physical_state,
        "connection_state": "online",
    }


_PROFILE = bundled_scene_profile()
_DECK_BOUNDS = _PROFILE.deck_bounds.to_dict()
_ANCHORS = {
    sensor_id: anchor.position
    for sensor_id, anchor in _PROFILE.sensor_anchors.items()
}


def test_pressure_field_is_bounded_and_identifies_peak_sensor() -> None:
    sensors = [
        _projected(reading("S01", value=600.0, sensor_type="strain"), "red"),
        _projected(reading("S02", value=100.0, sensor_type="strain"), "normal"),
        _projected(reading("S05", value=10.0, sensor_type="displacement"), "normal"),
    ]

    payload = build_pressure_update(
        sensors,
        _thresholds,
        deck_bounds=_DECK_BOUNDS,
        sensor_anchors=_ANCHORS,
        generated_at=1_700_000_000.0,
    )

    assert payload["type"] == "pressure_update"
    assert payload["coverage"] == 3
    assert payload["max_sensor_id"] == "S01"
    assert payload["max_level"] == "red"
    assert payload["grid"]["nx"] * payload["grid"]["nz"] == len(payload["values"])
    assert all(math.isfinite(value) for value in payload["values"])
    assert max(payload["values"]) <= 1.25
    assert len(json.dumps(payload, separators=(",", ":")).encode()) < MAX_SENSOR_UPDATE_BYTES


def test_pressure_field_reports_no_data_without_sensors() -> None:
    payload = build_pressure_update(
        [],
        _thresholds,
        deck_bounds=_DECK_BOUNDS,
        sensor_anchors=_ANCHORS,
    )

    assert payload["coverage"] == 0
    assert payload["max"] == 0.0
    assert payload["max_level"] == "unknown"
    assert payload["max_sensor_id"] is None
    assert set(payload["values"]) == {0.0}


def test_pressure_field_uses_profile_deck_bounds_and_anchors() -> None:
    payload = build_pressure_update(
        [_projected(reading("S01", value=100.0), "normal")],
        _thresholds,
        deck_bounds={
            "min_x": -50.0,
            "max_x": 50.0,
            "min_y": 0.0,
            "max_y": 2.0,
            "min_z": -5.0,
            "max_z": 5.0,
        },
        sensor_anchors={"S01": (10.0, 3.0, 2.0)},
        generated_at=1_700_000_000.0,
    )

    assert payload["grid"]["x_min"] == -50.0
    assert payload["grid"]["x_max"] == 50.0
    assert payload["grid"]["z_min"] == -5.0
    assert payload["grid"]["z_max"] == 5.0
    assert payload["points"][0]["x"] == 10.0
    assert payload["points"][0]["z"] == 2.0


def _frame_inputs():
    sensors = [
        _projected(reading("S01", value=600.0, sensor_type="strain"), "red"),
        _projected(reading("S02", value=150.0, sensor_type="strain"), "normal"),
        _projected(reading("S05", value=10.0, sensor_type="displacement"), "normal"),
    ]
    snapshot = LiveSensorSnapshot(sensors=sensors, alerts=[], stats={})
    pressure = build_pressure_update(
        sensors,
        _thresholds,
        deck_bounds=_DECK_BOUNDS,
        sensor_anchors=_ANCHORS,
        generated_at=1_700_000_000.0,
    )
    return snapshot, pressure


def _encoded_size(payload: Mapping[str, Any]) -> int:
    return len(encode_message(payload).encode("utf-8"))


def test_frame_assembler_records_full_pressure_without_omissions() -> None:
    snapshot, pressure = _frame_inputs()

    payload = LiveFrameAssembler().assemble(snapshot, pressure=pressure)

    assert payload["budget"] == {
        "limit_bytes": MAX_SENSOR_UPDATE_BYTES,
        "omissions": [],
    }
    assert payload["pressure"]["points"]
    assert _encoded_size(payload) <= MAX_SENSOR_UPDATE_BYTES


def test_frame_assembler_degrades_pressure_points_before_dropping_pressure() -> None:
    snapshot, pressure = _frame_inputs()
    full_size = _encoded_size(
        LiveFrameAssembler().assemble(
            snapshot,
            pressure=pressure,
        )
    )

    frame_limit = full_size - 100
    payload = LiveFrameAssembler(max_bytes=frame_limit).assemble(
        snapshot,
        pressure=pressure,
    )

    assert payload["budget"]["omissions"] == ["pressure.points"]
    assert payload["pressure"]["points"] == []
    assert payload["pressure"]["values"]
    assert _encoded_size(payload) <= frame_limit


def test_frame_assembler_reports_whole_pressure_omission() -> None:
    snapshot, pressure = _frame_inputs()
    no_pressure_size = _encoded_size(
        LiveFrameAssembler(max_bytes=10_000_000).assemble(
            snapshot,
            pressure=None,
        )
    )

    payload = LiveFrameAssembler(max_bytes=no_pressure_size + 40).assemble(
        snapshot,
        pressure=pressure,
    )

    assert "pressure" not in payload
    assert payload["budget"]["omissions"] == ["pressure"]
    assert _encoded_size(payload) <= no_pressure_size + 40


def test_response_field_api_uses_live_snapshot(client) -> None:
    records = [
        reading(
            sensor_id=f"S{index:02d}",
            value=float(index * 30),
            timestamp=1_700_000_000.0 + index,
        )
        for index in range(1, 9)
    ]
    assert client.post("/api/data/upload/json", json=records).status_code == 200

    response = client.get("/api/analysis/response-field")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["source"] == "live"
    assert payload["coverage"] == 8
    assert payload["threshold_profile"]["status"] == "provisional"
    assert len(payload["values"]) == payload["grid"]["nx"] * payload["grid"]["nz"]
    assert {point["sensor_id"] for point in payload["points"]} == {
        f"S{index:02d}" for index in range(1, 9)
    }
    assert {point["physical_state"] for point in payload["points"]} == {"normal"}


def test_response_field_api_rejects_timestamp_outside_history(client) -> None:
    response = client.get("/api/analysis/response-field", params={"timestamp": 1.0})

    assert response.status_code == 400
    assert "history" in response.json()["detail"]


def test_live_websocket_embeds_pressure_field_in_sensor_frame() -> None:
    services, app = create_live_app(
        simulator=OneShotSimulator(),
        interval_seconds=60.0,
    )

    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        with client.websocket_connect("/ws/live") as websocket:
            payload = websocket.receive_json()

    assert payload["type"] == "sensor_update"
    pressure = payload["pressure"]
    assert pressure["type"] == "pressure_update"
    assert pressure["coverage"] == 1
    assert pressure["points"][0]["sensor_id"] == "S01"
    assert pressure["points"][0]["physical_state"] in {
        "normal",
        "yellow",
        "orange",
        "red",
        "unknown",
    }
