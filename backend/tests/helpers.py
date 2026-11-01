"""Shared test helpers."""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Self, cast

from app.dependencies import AppServices, create_services
from app.engine.data_engine import MonitoringEngine
from app.live_contract import SensorUpdateWire
from app.live_stream import LiveFrameSink
from app.main import create_app
from app.sensor_batch import LiveEligibility, SensorBatch
from app.sensor_reading import SensorReadingRecord
from fastapi import FastAPI

from tests.factories import reading


@dataclass
class TrackingLock:
    """Re-entrant lock that records acquisition and ownership."""

    def __post_init__(self) -> None:
        self._lock = threading.RLock()
        self.acquisitions = 0
        self.held = False

    def __enter__(self) -> Self:
        self._lock.acquire()
        self.acquisitions += 1
        self.held = True
        return self

    def __exit__(self, *args: object) -> None:
        self.held = False
        self._lock.release()


def create_live_app(
    *,
    simulator: Any | None = None,
    interval_seconds: float | None = None,
    autostart: bool = False,
) -> tuple[AppServices, FastAPI]:
    services = create_services()
    services.live_stream_autostart = autostart
    if simulator is not None:
        services.simulator = simulator
    if interval_seconds is not None:
        services.live_stream_interval_seconds = interval_seconds
    return services, create_app(services)


def wait_until(predicate: Callable[[], bool], timeout: float = 1.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


async def async_wait_until(
    predicate: Callable[[], bool],
    timeout: float = 1.0,
) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.01)
    return predicate()


class CapturingManager:
    def __init__(self) -> None:
        self.payloads: list[SensorUpdateWire] = []

    def enqueue_broadcast(
        self,
        frame: SensorUpdateWire,
        *,
        budget_started_at: float | None = None,
    ) -> None:
        self.payloads.append(frame)


@dataclass
class PublisherEnvironment:
    engine: MonitoringEngine
    ws_manager: LiveFrameSink
    processing_lock: threading.RLock


class OneShotSimulator:
    is_running = False

    def next_readings(self, timestamp=None):
        self.is_running = False
        return [reading(timestamp=timestamp or 1_700_000_000.0)]


def install_capturing_manager(application: FastAPI) -> CapturingManager:
    """Route every live broadcast through one capturing manager."""
    manager = CapturingManager()
    services = application.state.services
    services.ws_manager = manager
    return manager


def ingest_records(
    engine,
    records: list[SensorReadingRecord],
    *,
    live_eligibility: LiveEligibility = LiveEligibility.INTERNAL,
) -> None:
    engine.ingest(
        SensorBatch(
            records=records,
            live_eligibility=live_eligibility,
        )
    )


def ingest_numbered_sensors(engine, count: int = 40) -> None:
    """Ingest timestamp-ordered readings for repeatedly numbered test sensors."""
    ingest_records(
        engine,
        [
            cast(
                SensorReadingRecord,
                reading(
                    sensor_id=f"S{index:03d}",
                    value=float(index),
                    timestamp=float(index),
                ),
            )
            for index in range(count)
        ],
    )
