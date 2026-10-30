"""Validation helpers for atomic sensor-data batches."""

from __future__ import annotations

import csv
import io
import math
from typing import Any

from app.sensor_ids import SensorIdentifier
from app.sensor_types import SensorType

SENSOR_TYPES = frozenset(sensor_type.value for sensor_type in SensorType)
REQUIRED_FIELDS = ("sensor_id", "name", "type", "value", "timestamp")
MAX_BATCH_SIZE = 10_000


class IngestionValidationError(ValueError):
    """A malformed batch that must be rejected before any state changes."""


def validate_json_batch(data: Any) -> list[dict]:
    """Validate a JSON array and return normalized sensor records."""
    if not isinstance(data, list):
        raise IngestionValidationError("request body must be a JSON array")

    if len(data) > MAX_BATCH_SIZE:
        raise IngestionValidationError(
            f"batch size {len(data)} exceeds the maximum of {MAX_BATCH_SIZE}"
        )

    return [_validate_json_record(item, index) for index, item in enumerate(data)]


def validate_csv_batch(content: bytes) -> list[dict]:
    """Validate a UTF-8 CSV file and return normalized sensor records."""
    if not content:
        return []

    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise IngestionValidationError("CSV file must be encoded as UTF-8") from exc

    if not text.strip():
        return []

    try:
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            return []

        fieldnames = [name.strip() for name in reader.fieldnames]
        missing_headers = [field for field in REQUIRED_FIELDS if field not in fieldnames]
        if missing_headers:
            raise IngestionValidationError(
                "CSV missing required column(s): " + ", ".join(missing_headers)
            )

        records: list[dict] = []
        for index, raw_row in enumerate(reader, start=1):
            row = {
                (key.strip() if isinstance(key, str) else key): value
                for key, value in raw_row.items()
            }
            if not any(_has_text(value) for value in row.values()):
                continue
            if len(records) >= MAX_BATCH_SIZE:
                raise IngestionValidationError(
                    f"batch size exceeds the maximum of {MAX_BATCH_SIZE}"
                )
            records.append(_validate_csv_record(row, index))
        return records
    except csv.Error as exc:
        raise IngestionValidationError(f"invalid CSV file: {exc}") from exc


def _validate_json_record(item: Any, index: int) -> dict:
    if not isinstance(item, dict):
        raise IngestionValidationError(f"record {index}: must be a JSON object")

    _require_fields(item, index)

    return {
        "sensor_id": _validated_sensor_identifier(item["sensor_id"], index),
        "name": _validated_text(item["name"], index, "name"),
        "type": _validated_sensor_type(item["type"], index),
        "value": _validated_json_number(item["value"], index, "value"),
        "timestamp": _validated_json_number(item["timestamp"], index, "timestamp"),
    }


def _validate_csv_record(row: dict, index: int) -> dict:
    raw_value = row.get("value")
    raw_timestamp = row.get("timestamp")
    return {
        "sensor_id": _validated_sensor_identifier(row.get("sensor_id"), index),
        "name": _validated_text(row.get("name"), index, "name"),
        "type": _validated_sensor_type(row.get("type"), index),
        "value": _validated_csv_number(raw_value, index, "value"),
        "timestamp": _validated_csv_number(raw_timestamp, index, "timestamp"),
    }


def _require_fields(item: dict, index: int) -> None:
    missing = [field for field in REQUIRED_FIELDS if field not in item]
    if missing:
        raise IngestionValidationError(
            f"record {index}: missing required field(s): {', '.join(missing)}"
        )


def _validated_text(value: Any, index: int, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise IngestionValidationError(
            f"record {index}: {field} must be a non-empty string"
        )
    return value.strip()


def _validated_sensor_identifier(
    value: Any,
    index: int,
) -> SensorIdentifier:
    if not isinstance(value, str):
        raise IngestionValidationError(
            f"record {index}: sensor_id must be a non-empty string"
        )
    try:
        return SensorIdentifier(value)
    except ValueError as exc:
        raise IngestionValidationError(
            f"record {index}: sensor_id must be a non-empty string"
        ) from exc


def _validated_sensor_type(value: Any, index: int) -> SensorType:
    if not isinstance(value, str):
        raise IngestionValidationError(f"record {index}: type must be a string")
    sensor_type = value.strip()
    try:
        return SensorType(sensor_type)
    except ValueError as exc:
        allowed = ", ".join(sorted(SENSOR_TYPES))
        raise IngestionValidationError(
            f"record {index}: unknown sensor type '{sensor_type}'; expected one of {allowed}"
        ) from exc


def _validated_json_number(value: Any, index: int, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise IngestionValidationError(f"record {index}: {field} must be a number")
    result = float(value)
    if not math.isfinite(result):
        raise IngestionValidationError(f"record {index}: {field} must be finite")
    return result


def _validated_csv_number(value: Any, index: int, field: str) -> float:
    if not _has_text(value):
        raise IngestionValidationError(f"record {index}: {field} must be a number")
    try:
        result = float(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise IngestionValidationError(
            f"record {index}: {field} must be a number"
        ) from exc
    if not math.isfinite(result):
        raise IngestionValidationError(f"record {index}: {field} must be finite")
    return result


def _has_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())
