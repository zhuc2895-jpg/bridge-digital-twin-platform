import pytest

from app.sensor_ids import SensorIdentifier


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
