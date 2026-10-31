"""Shared test helpers."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
import threading
import time
from typing import Any

from fastapi import FastAPI

from app.dependencies import AppServices, create_services
from app.main import create_app
from app.sensor_batch import LiveEligibility, SensorBatch


@dataclass
class TrackingLock:
    """Re-entrant lock that records acquisition and ownership."""

    def __post_init__(self) -> None:
        self._lock = threading.RLock()
        self.acquisitions = 0
        self.held = False

    def __enter__(self) -> TrackingLock:
        self._lock.acquire()
        self.acquisitions += 1
        self.held = True
        return self

    def __exit__(self, *args: Any) -> None:
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
        self.payloads: list[dict[str, Any]] = []

    def enqueue_broadcast(self, payload, *, queued_at=None):
        self.payloads.append(payload)

def ingest_records(
    engine,
    records: list[dict],
    *,
    live_eligibility: LiveEligibility = LiveEligibility.INTERNAL,
) -> None:
    engine.ingest(
        SensorBatch.from_records(
            records,
            live_eligibility=live_eligibility,
        )
    )
