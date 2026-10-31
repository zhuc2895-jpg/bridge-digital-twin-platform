"""Shared JSON message encoding and byte limits."""

from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

MAX_SENSOR_UPDATE_BYTES = 10 * 1024


def encode_message(data: Mapping[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))
