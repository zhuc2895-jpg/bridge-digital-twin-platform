"""Configuration, CORS, log safety, error isolation, and health degradation."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Mapping

import pytest
from app.config import AppConfig
from app.dependencies import create_services
from app.ingestion import validate_live_json_records
from app.main import create_app
from app.observability import (
    MAX_LOG_MESSAGE_CHARS,
    REQUEST_ID_HEADER,
    SensitiveDataFilter,
    redact_text,
    stable_error_payload,
)
from app.sensor_batch import LiveEligibility, SensorBatch
from fastapi.testclient import TestClient

from tests.factories import reading


class FailingCheckpointStore:
    def load(self) -> dict[str, Any] | None:
        return None

    def save(self, payload: Mapping[str, Any]) -> None:
        raise OSError("checkpoint disk unavailable")


def _app_with_config(config: AppConfig):
    services = create_services(config=config)
    services.live_stream_autostart = False
    return services, create_app(services, config=config)


def test_config_from_env_overrides_runtime_and_algorithm_settings(
    tmp_path: Path,
) -> None:
    checkpoint = tmp_path / "configured-state.json"
    config = AppConfig.from_env(
        {
            "BRIDGE_HOST": "127.0.0.1",
            "BRIDGE_PORT": "9100",
            "BRIDGE_CHECKPOINT_PATH": str(checkpoint),
            "BRIDGE_LOG_LEVEL": "debug",
            "BRIDGE_CORS_ORIGINS": "https://a.example, https://b.example",
            "BRIDGE_SIMULATION_ENABLED": "false",
            "BRIDGE_LIVE_INTERVAL_SECONDS": "2.5",
            "BRIDGE_STRAIN_YELLOW": "310",
            "BRIDGE_STRAIN_ORANGE": "460",
            "BRIDGE_STRAIN_RED": "620",
            "BRIDGE_AI_CONFIDENCE_THRESHOLD": "0.82",
            "BRIDGE_AI_MIN_VOTES": "3",
            "BRIDGE_FEATURE_MEAN_SHIFT_THRESHOLD": "2.4",
            "BRIDGE_FEATURE_VARIANCE_THRESHOLD": "2.5",
            "BRIDGE_FEATURE_TREND_THRESHOLD": "2.6",
            "BRIDGE_SPATIAL_RESIDUAL_THRESHOLD": "2.8",
            "BRIDGE_SPATIAL_MIN_TRAINING_SNAPSHOTS": "40",
            "BRIDGE_SPATIAL_MIN_SENSORS": "4",
            "BRIDGE_SPATIAL_MIN_COHERENT_SENSORS": "3",
            "BRIDGE_SPATIAL_ALPHA": "0.02",
            "BRIDGE_SPATIAL_WEIGHTS": '{"S03": 1.5}',
        }
    )

    assert config.host == "127.0.0.1"
    assert config.port == 9100
    assert config.checkpoint_path == checkpoint
    assert config.log_level == "DEBUG"
    assert config.cors_origins == ("https://a.example", "https://b.example")
    assert config.simulation_enabled is False
    assert config.live_interval_seconds == 2.5
    assert config.spatial_residual_threshold == 2.8
    assert config.spatial_min_training_snapshots == 40
    assert config.spatial_min_sensors == 4
    assert config.spatial_min_coherent_sensors == 3
    assert config.spatial_alpha == 0.02
    assert config.spatial_weights == {"S03": 1.5}
    assert config.thresholds["strain"] == {
        "yellow": 310.0,
        "orange": 460.0,
        "red": 620.0,
    }

    services = create_services(config=config, persistence_enabled=True)
    assert services.engine.thresholds == config.thresholds
    assert services.live_stream_autostart is False
    assert services.live_stream_interval_seconds == 2.5
    assert services.persistence is not None
    assert services.persistence.store.path == checkpoint
    ensemble = services.detectors.registry.get("ensemble")
    assert ensemble.parameters["confidence_threshold"] == 0.82
    assert ensemble.parameters["min_votes"] == 3
    assert ensemble.parameters["feature_arbitration"][
        "mean_shift_threshold"
    ] == 2.4
    assert ensemble.parameters["feature_arbitration"][
        "variance_change_threshold"
    ] == 2.5
    assert ensemble.parameters["feature_arbitration"][
        "trend_slope_threshold"
    ] == 2.6
    assert ensemble.parameters["feature_arbitration"]["spatial_residual"][
        "residual_threshold"
    ] == 2.8
    assert ensemble.parameters["feature_arbitration"]["spatial_residual"][
        "weights"
    ] == {"S03": 1.5}


@pytest.mark.parametrize(
    "kwargs",
    [
        {"cors_origins": ("*",)},
        {"cors_origins": ()},
        {"port": 0},
        {"log_level": "verbose"},
        {"ai_confidence_threshold": 1.1},
        {"ai_min_votes": 1},
        {"feature_mean_shift_threshold": 0},
        {"spatial_residual_threshold": 0},
        {"spatial_min_sensors": 1},
        {"spatial_min_coherent_sensors": 5},
        {"spatial_weights": {"S01": 0}},
        {
            "thresholds": {
                "strain": {"yellow": 300, "orange": 200, "red": 600},
                "displacement": {"yellow": 30, "orange": 50, "red": 80},
                "acceleration": {"yellow": 2, "orange": 3.5, "red": 5},
                "temperature": {"yellow": 45, "orange": 55, "red": 65},
            }
        },
    ],
)
def test_invalid_configuration_is_rejected(kwargs) -> None:
    with pytest.raises(ValueError):
        AppConfig(**kwargs)


def test_cors_allows_configured_origin_and_rejects_others() -> None:
    config = AppConfig(
        cors_origins=("https://allowed.example",),
        simulation_enabled=False,
    )
    _, application = _app_with_config(config)
    with TestClient(application) as client:
        allowed = client.get("/", headers={"Origin": "https://allowed.example"})
        denied = client.get("/", headers={"Origin": "https://denied.example"})
        preflight = client.options(
            "/api/data/upload/json",
            headers={
                "Origin": "https://allowed.example",
                "Access-Control-Request-Method": "POST",
            },
        )

    assert allowed.headers["access-control-allow-origin"] == "https://allowed.example"
    assert "access-control-allow-origin" not in denied.headers
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == "https://allowed.example"


def test_invalid_upload_is_400_atomic_and_logged_without_payload(
    caplog: pytest.LogCaptureFixture,
) -> None:
    config = AppConfig(simulation_enabled=False)
    services, application = _app_with_config(config)
    invalid_batch = [
        reading(name="password=do-not-log"),
        {"sensor_id": "S02", "type": "strain", "value": 1.0, "timestamp": 2.0},
    ]
    with caplog.at_level("WARNING", logger="app.api.routes_data"):
        with TestClient(application) as client:
            response = client.post("/api/data/upload/json", json=invalid_batch)

    assert response.status_code == 400
    assert "missing required field" in response.json()["detail"]
    assert services.engine.get_sensor_count() == 0
    assert "Rejected JSON upload" in caplog.text
    assert "IngestionValidationError" in caplog.text
    assert "do-not-log" not in caplog.text


def test_live_bad_record_is_skipped_logged_and_following_record_survives(
    caplog: pytest.LogCaptureFixture,
) -> None:
    raw = [
        reading(sensor_id="S-bad", value="not-a-number"),
        reading(sensor_id="S-good", value=42.0, timestamp=1001.0),
    ]
    with caplog.at_level("WARNING", logger="app.ingestion"):
        records = validate_live_json_records(raw)

    assert [record["sensor_id"] for record in records] == ["S-good"]
    assert "Skipping invalid live reading" in caplog.text
    assert "S-bad" in caplog.text

    config = AppConfig(simulation_enabled=False)
    services, _ = _app_with_config(config)
    services.processor.process(
        SensorBatch(records=records, live_eligibility=LiveEligibility.INTERNAL)
    )
    assert services.engine.get_latest("S-good") is not None


def test_sensitive_filter_redacts_credentials_and_caps_message_size() -> None:
    filter_instance = SensitiveDataFilter()
    record = logging.LogRecord(
        "app.test",
        logging.INFO,
        __file__,
        1,
        "Authorization: Bearer abc.def token=top-secret password=hunter2 payload=%s",
        ("x" * (MAX_LOG_MESSAGE_CHARS + 500),),
        None,
    )

    assert filter_instance.filter(record) is True
    rendered = record.getMessage()
    assert "abc.def" not in rendered
    assert "top-secret" not in rendered
    assert "hunter2" not in rendered
    assert "[REDACTED]" in rendered
    assert rendered.endswith("...[truncated]")
    assert len(rendered) <= MAX_LOG_MESSAGE_CHARS + len("...[truncated]")


def test_request_logging_does_not_include_body_or_headers(
    caplog: pytest.LogCaptureFixture,
) -> None:
    config = AppConfig(simulation_enabled=False)
    _, application = _app_with_config(config)
    with caplog.at_level("INFO", logger="app.main"):
        with TestClient(application) as client:
            response = client.post(
                "/api/data/upload/json",
                headers={"Authorization": "Bearer header-secret"},
                json=[reading(name="token=payload-secret")],
            )

    assert response.status_code == 200
    assert "request_completed" in caplog.text
    assert "header-secret" not in caplog.text
    assert "payload-secret" not in caplog.text


def test_unhandled_exception_is_stable_safe_and_redacted(
    caplog: pytest.LogCaptureFixture,
) -> None:
    config = AppConfig(simulation_enabled=False)
    _, application = _app_with_config(config)

    @application.get("/test/fail")
    async def fail():
        raise RuntimeError("password=hunter2 failed in internal/path.py")

    with caplog.at_level("ERROR", logger="app.main"):
        with TestClient(application, raise_server_exceptions=False) as client:
            response = client.get(
                "/test/fail",
                headers={REQUEST_ID_HEADER: "request-123"},
            )

    assert response.status_code == 500
    assert response.json() == stable_error_payload("request-123")
    assert response.headers[REQUEST_ID_HEADER] == "request-123"
    assert "RuntimeError" not in response.text
    assert "hunter2" not in response.text
    assert "Traceback" not in response.text
    assert "error_type=RuntimeError" in caplog.text
    assert "hunter2" not in caplog.text


def test_health_degrades_when_persistence_fails() -> None:
    config = AppConfig(simulation_enabled=False)
    services = create_services(
        config=config,
        checkpoint_store=FailingCheckpointStore(),
    )
    services.live_stream_autostart = False
    services.processor.process(SensorBatch(records=[reading()]))
    application = create_app(services, config=config)

    with TestClient(application) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "degraded"
    assert payload["checks"]["persistence"]["status"] == "degraded"
    assert payload["persistence"]["last_error"]


def test_simulation_switch_blocks_live_start_and_injection() -> None:
    config = AppConfig(simulation_enabled=False)
    services, application = _app_with_config(config)

    with TestClient(application) as client:
        injection = client.post(
            "/api/analysis/inject-anomaly",
            json={"sensor_id": "S01"},
        )
        health = client.get("/api/health").json()

    assert services.live_stream.is_running is False
    assert injection.status_code == 503
    assert health["simulator_running"] is False


def test_redact_text_handles_query_style_and_bearer_credentials() -> None:
    rendered = redact_text("url?api_key=secret-value Authorization: Bearer abc123")
    assert "secret-value" not in rendered
    assert "abc123" not in rendered
