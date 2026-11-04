"""Stable read-side access to retained monitoring history and alerts."""

from __future__ import annotations

import math
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any

from app.engine.data_engine import MonitoringEngine


class HistoryReadError(ValueError):
    """A requested history read cannot be satisfied from retained state."""


class HistoryUnavailableError(HistoryReadError):
    """No retained history exists for the requested read."""


class HistoryTimestampOutOfRangeError(HistoryReadError):
    """A requested timestamp lies outside the retained history window."""


class HistorySnapshotMissingError(HistoryReadError):
    """No sensor snapshot exists at the requested retained timestamp."""


@dataclass(frozen=True, slots=True)
class ReportReadSnapshot:
    alerts: list[dict]
    latest: dict[str, dict]
    time_valid_latest: dict[str, dict]
    period_reading_count: int
    stats: dict[str, Any]


class HistoryReadModel:
    """Generate stable history reads inside the shared mutation boundary."""

    def __init__(
        self,
        engine: MonitoringEngine,
        lock: AbstractContextManager[object],
    ) -> None:
        self._engine = engine
        self._lock = lock

    def time_range(self) -> dict:
        with self._lock:
            return self._engine.get_time_range()

    def latest(self, sensor_id: str | None = None) -> dict | None:
        with self._lock:
            return self._engine.get_latest(sensor_id)

    def history_range(
        self,
        sensor_id: str,
        start_ts: float,
        end_ts: float,
        max_points: int,
    ) -> list[dict]:
        with self._lock:
            return self._engine.get_history_range(
                sensor_id,
                start_ts,
                end_ts,
                max_points,
            )

    def snapshot_at(self, timestamp: float) -> dict:
        if not math.isfinite(timestamp):
            raise HistoryReadError("timestamp must be finite")
        with self._lock:
            return self._engine.get_snapshot_at(timestamp)

    def alerts_range(self, start_ts: float, end_ts: float) -> list[dict]:
        with self._lock:
            return self._engine.get_alerts_range(start_ts, end_ts)

    def recent_alerts(self) -> list[dict]:
        with self._lock:
            return self._engine.get_recent_alerts()

    def alert_stats(self) -> dict:
        with self._lock:
            return self._engine.get_alert_stats()

    def recent_history(self, sensor_id: str, minutes: int) -> list[dict]:
        with self._lock:
            return self._engine.get_history(sensor_id, minutes)

    def sensor_stats(self, sensor_id: str) -> dict | None:
        with self._lock:
            return self._engine.get_sensor_stats(sensor_id)

    def top_spikes(self) -> list[dict]:
        with self._lock:
            return self._engine.get_top_spikes()

    def live_snapshot(self, limit: int = 32) -> list[dict]:
        with self._lock:
            return self._engine.get_live_snapshot(limit=limit)

    def threshold_profile_summary(self) -> dict[str, str]:
        with self._lock:
            return self._engine.threshold_profile_summary()

    def latest_retained_snapshot(self) -> tuple[float, dict]:
        with self._lock:
            time_range = self._engine.get_time_range()
            if not time_range["has_data"]:
                raise HistoryUnavailableError("No sensor history is available")
            timestamp = float(time_range["end"])
            snapshot = self._engine.get_snapshot_at(timestamp)
            if not snapshot:
                raise HistorySnapshotMissingError(
                    "No sensor snapshot exists at the requested timestamp"
                )
            return timestamp, snapshot

    def snapshot_at_retained_time(self, timestamp: float) -> dict:
        if not math.isfinite(timestamp):
            raise HistoryReadError("timestamp must be finite")
        with self._lock:
            time_range = self._engine.get_time_range()
            if not time_range["has_data"]:
                raise HistoryUnavailableError("No sensor history is available")
            if not time_range["start"] <= timestamp <= time_range["end"]:
                raise HistoryTimestampOutOfRangeError(
                    "timestamp is outside the retained sensor history"
                )
            snapshot = self._engine.get_snapshot_at(timestamp)
            if not snapshot:
                raise HistorySnapshotMissingError(
                    "No sensor snapshot exists at the requested timestamp"
                )
            return snapshot

    def report_snapshot(
        self,
        start_ts: float,
        end_ts: float,
    ) -> ReportReadSnapshot:
        with self._lock:
            return ReportReadSnapshot(
                alerts=self._engine.get_alerts_range(start_ts, end_ts),
                latest=self._engine.get_latest() or {},
                time_valid_latest=self._engine.get_latest_time_valid(end_ts),
                period_reading_count=self._engine.get_period_reading_count(
                    start_ts,
                    end_ts,
                ),
                stats=self._engine.get_stats(reference_time=end_ts),
            )
