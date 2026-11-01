import pytest
from app.sensor_ids import SensorIdentifier, validate_live_sensor_identifier


def test_sensor_identifier_trims_surrounding_whitespace():
    sensor_id = SensorIdentifier(" S01 ")

    assert sensor_id == "S01"
    assert str(sensor_id) == "S01"


def test_sensor_identifier_rejects_blank_value():
    with pytest.raises(ValueError, match="sensor_id is required"):
        SensorIdentifier("   ")


def test_sensor_identifier_has_string_identity():
    sensor_id = SensorIdentifier("S01")

    assert sensor_id == "S01"
    assert hash(sensor_id) == hash("S01")


def test_live_sensor_identifier_limits_utf8_wire_bytes():
    with pytest.raises(ValueError, match="64 UTF-8 bytes"):
        validate_live_sensor_identifier(SensorIdentifier("😀" * 17))


def test_sensor_identifier_rejects_unpaired_surrogate():
    with pytest.raises(ValueError, match="valid Unicode"):
        SensorIdentifier("S\ud800")
