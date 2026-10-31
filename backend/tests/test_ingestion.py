import time

from app.dependencies import create_services
from app.ingestion import validate_json_batch
from app.main import create_app
from app.sensor_ids import SensorIdentifier
from app.sensor_types import SensorType
from fastapi.testclient import TestClient

from tests.factories import reading
from tests.helpers import CapturingManager


def csv_text(rows: list[dict]) -> str:
    header = "sensor_id,name,type,value,timestamp\n"
    body = "".join(
        f"{row['sensor_id']},{row['name']},{row['type']},{row['value']},{row['timestamp']}\n"
        for row in rows
    )
    return header + body


def assert_empty_sensor_state(client: TestClient) -> None:
    response = client.get("/api/sensors/")
    assert response.status_code == 200
    assert response.json() == {}


def test_json_validation_retains_domain_types():
    record = validate_json_batch([reading()])[0]

    assert isinstance(record["sensor_id"], SensorIdentifier)
    assert isinstance(record["type"], SensorType)


def test_json_upload_updates_latest_state_and_health(client, app):
    capturing_manager = CapturingManager()
    app.state.services.ws_manager = capturing_manager
    app.state.services.sensor_updates.ws_manager = capturing_manager

    response = client.post(
        "/api/data/upload/json",
        json=[
            reading(),
            reading(
                sensor_id="S02",
                name="Tower displacement",
                sensor_type="displacement",
                value=90.0,
                timestamp=1_700_000_001.0,
            ),
        ],
    )

    assert response.status_code == 200
    assert capturing_manager.payloads == []
    assert response.json() == {
        "status": "ok",
        "records_ingested": 2,
        "alerts_triggered": 1,
        "sensors_updated": 2,
    }

    latest = client.get("/api/sensors/").json()
    assert set(latest) == {"S01", "S02"}
    assert latest["S01"] == reading()
    assert latest["S02"]["value"] == 90.0

    single = client.get("/api/sensors/S01")
    assert single.status_code == 200
    assert single.json() == reading()

    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["status"] == "healthy"
    assert health.json()["sensor_count"] == 2
    assert health.json()["retained_alerts"] == 1
    assert "recent_alerts" not in health.json()
    assert "active_alerts" not in health.json()
    assert health.json()["simulator_running"] is False
    assert health.json()["state_scope"] == "process"


def test_push_live_openapi_documents_live_eligibility(client):
    paths = client.get("/openapi.json").json()["paths"]
    operations = [
        paths["/api/data/upload/csv"]["post"],
        paths["/api/data/upload/json"]["post"],
        paths["/api/data/upload/single"]["post"],
    ]

    descriptions = [
        parameter["description"]
        for operation in operations
        for parameter in operation.get("parameters", [])
        if parameter["name"] == "push_live"
    ]

    assert len(descriptions) == 3
    assert all("Live Eligibility" in description for description in descriptions)


def test_push_live_controls_live_eligibility(client):
    backfill = client.post(
        "/api/data/upload/json?push_live=false",
        json=[reading(sensor_id="BACKFILL", value=900.0, timestamp=200.0)],
    )
    live = client.post(
        "/api/data/upload/json?push_live=true",
        json=[reading(sensor_id="LIVE", value=100.0, timestamp=100.0)],
    )

    assert backfill.status_code == 200
    assert live.status_code == 200
    assert client.get("/api/sensors/BACKFILL").json()["value"] == 900.0
    assert [
        item["sensor_id"]
        for item in client.app.state.services.engine.get_live_snapshot()
    ] == ["LIVE"]


def test_json_ingestion_normalizes_sensor_identifier_whitespace(client):
    response = client.post(
        "/api/data/upload/json?push_live=false",
        json=[reading(sensor_id=" S02 ")],
    )

    assert response.status_code == 200
    assert client.get("/api/sensors/S02").status_code == 200


def test_csv_upload_and_push_live_false_are_accepted(client, app):
    capturing_manager = CapturingManager()
    app.state.services.ws_manager = capturing_manager
    app.state.services.sensor_updates.ws_manager = capturing_manager

    response = client.post(
        "/api/data/upload/csv?push_live=false",
        files={
            "file": (
                "readings.csv",
                csv_text([reading(sensor_id="CSV-01")]),
                "text/csv",
            )
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "records_ingested": 1,
        "alerts_triggered": 0,
        "sensors_updated": 1,
    }
    assert capturing_manager.payloads == []
    assert client.get("/api/sensors/CSV-01").json() == reading(sensor_id="CSV-01")


def test_json_missing_field_rejects_whole_batch_without_writes(client):
    invalid = reading(sensor_id="S02")
    invalid.pop("timestamp")

    response = client.post(
        "/api/data/upload/json",
        json=[reading(), invalid],
    )

    assert response.status_code == 400
    assert "timestamp" in response.json()["detail"]
    assert_empty_sensor_state(client)


def test_csv_invalid_value_rejects_whole_batch_without_writes(client):
    content = csv_text([reading()]).replace(",100.0,", ",not-a-number,")

    response = client.post(
        "/api/data/upload/csv",
        files={"file": ("bad.csv", content, "text/csv")},
    )

    assert response.status_code == 400
    assert "value" in response.json()["detail"]
    assert_empty_sensor_state(client)


def test_unknown_sensor_type_is_rejected(client):
    response = client.post(
        "/api/data/upload/json",
        json=[reading(sensor_type="wind")],
    )

    assert response.status_code == 400
    assert "type" in response.json()["detail"]
    assert_empty_sensor_state(client)


def test_empty_json_and_csv_batches_are_accepted_without_writes(client):
    json_response = client.post("/api/data/upload/json", json=[])
    assert json_response.status_code == 200
    assert json_response.json() == {
        "status": "ok",
        "records_ingested": 0,
        "alerts_triggered": 0,
        "sensors_updated": 0,
    }

    csv_response = client.post(
        "/api/data/upload/csv",
        files={
            "file": (
                "empty.csv",
                "sensor_id,name,type,value,timestamp\n",
                "text/csv",
            )
        },
    )
    assert csv_response.status_code == 200
    assert csv_response.json()["records_ingested"] == 0
    assert_empty_sensor_state(client)


def test_10000_records_are_visible_within_500ms(client):
    records = [
        reading(
            value=100.0,
            timestamp=1_700_000_000.0 + index / 1000,
        )
        for index in range(10_000)
    ]

    started = time.perf_counter()
    response = client.post("/api/data/upload/json", json=records)
    latest = client.get("/api/sensors/S01")
    elapsed = time.perf_counter() - started

    assert response.status_code == 200
    assert response.json()["records_ingested"] == 10_000
    assert response.json()["sensors_updated"] == 1
    assert latest.status_code == 200
    assert latest.json()["value"] == 100.0
    assert latest.json()["timestamp"] == records[-1]["timestamp"]
    assert elapsed <= 0.5


def test_10001_json_records_are_rejected_without_writes(client):
    records = [reading(timestamp=1_700_000_000.0 + index) for index in range(10_001)]

    response = client.post("/api/data/upload/json", json=records)

    assert response.status_code == 400
    assert "10000" in response.json()["detail"]
    assert client.get("/api/sensors/S01").status_code == 404


def test_10001_csv_records_are_rejected_without_writes(client):
    records = [reading(timestamp=1_700_000_000.0 + index) for index in range(10_001)]

    response = client.post(
        "/api/data/upload/csv",
        files={"file": ("too-many.csv", csv_text(records), "text/csv")},
    )

    assert response.status_code == 400
    assert "10000" in response.json()["detail"]
    assert_empty_sensor_state(client)


def test_app_instances_do_not_share_state():
    first_services = create_services()
    first_services.live_stream_autostart = False
    second_services = create_services()
    second_services.live_stream_autostart = False
    first_app = create_app(first_services)
    second_app = create_app(second_services)

    with TestClient(first_app) as first_client:
        assert first_client.post("/api/data/upload/json", json=[reading()]).status_code == 200

    with TestClient(second_app) as second_client:
        assert second_client.get("/api/sensors/").json() == {}


def test_csv_missing_required_column_is_rejected(client):
    content = "sensor_id,name,type,value\nS01,Main span strain,strain,100.0\n"

    response = client.post(
        "/api/data/upload/csv",
        files={"file": ("missing-column.csv", content, "text/csv")},
    )

    assert response.status_code == 400
    assert "timestamp" in response.json()["detail"]
    assert_empty_sensor_state(client)


def test_json_non_numeric_value_is_rejected(client):
    invalid = reading()
    invalid["value"] = "100.0"

    response = client.post("/api/data/upload/json", json=[invalid])

    assert response.status_code == 400
    assert "value" in response.json()["detail"]
    assert_empty_sensor_state(client)


def test_latest_state_uses_timestamp_not_request_order(client):
    response = client.post(
        "/api/data/upload/json",
        json=[
            reading(value=200.0, timestamp=200.0),
            reading(value=100.0, timestamp=100.0),
        ],
    )

    assert response.status_code == 200
    latest = client.get("/api/sensors/S01")
    assert latest.status_code == 200
    assert latest.json()["value"] == 200.0
    assert latest.json()["timestamp"] == 200.0


def test_health_counts_all_retained_alerts_beyond_recent_twenty(client):
    records = [
        reading(value=600.0, timestamp=1_700_000_000.0 + index * 10)
        for index in range(21)
    ]

    response = client.post("/api/data/upload/json", json=records)

    assert response.status_code == 200
    assert response.json()["alerts_triggered"] == 21
    assert client.get("/api/health").json()["retained_alerts"] == 21


def test_10000_csv_records_are_visible_within_500ms(client):
    records = [
        reading(value=100.0, timestamp=1_700_000_000.0 + index / 1000)
        for index in range(10_000)
    ]

    started = time.perf_counter()
    response = client.post(
        "/api/data/upload/csv",
        files={"file": ("large.csv", csv_text(records), "text/csv")},
    )
    latest = client.get("/api/sensors/S01")
    elapsed = time.perf_counter() - started

    assert response.status_code == 200
    assert response.json()["records_ingested"] == 10_000
    assert response.json()["sensors_updated"] == 1
    assert latest.status_code == 200
    assert latest.json()["value"] == 100.0
    assert elapsed <= 0.5


def test_csv_blank_rows_after_limit_are_ignored(client):
    records = [
        reading(value=100.0, timestamp=1_700_000_000.0 + index / 1000)
        for index in range(10_000)
    ]

    response = client.post(
        "/api/data/upload/csv",
        files={
            "file": (
                "large-with-blank-rows.csv",
                csv_text(records) + ",,,,\n\n",
                "text/csv",
            )
        },
    )

    assert response.status_code == 200
    assert response.json()["records_ingested"] == 10_000
    assert response.json()["sensors_updated"] == 1


def test_request_validation_is_400_only_for_documented_endpoints(client):
    upload_response = client.post(
        "/api/data/upload/json",
        json={"sensor_id": "S01"},
    )
    history_response = client.get(
        "/api/sensors/history/range",
        params={
            "sensor_id": "S01",
            "start": 0,
            "end": 1,
            "max_points": 1,
        },
    )
    unrelated_response = client.get(
        "/api/sensors/history/snapshot",
        params={"ts": "not-a-number"},
    )

    assert upload_response.status_code == 400
    assert history_response.status_code == 400
    assert unrelated_response.status_code == 422
