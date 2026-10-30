import pytest

from app.sensor_types import SensorType


def test_sensor_type_rejects_unknown_value():
    with pytest.raises(ValueError):
        SensorType("unknown")
