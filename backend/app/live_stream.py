"""Application-scoped live stream publishing and thread lifecycle."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Protocol, cast

from app.bridge_scene_profile import BridgeSceneProfile, bundled_scene_profile
from app.engine.data_engine import MonitoringEngine
from app.engine.simulator import DataSimulator
from app.ingestion import validate_live_json_records
from app.live_contract import (
    AlertSnapshotRecord,
    LiveSensorSnapshot,
    SensorReadingWire,
    SensorUpdateWire,
    build_sensor_update_from_snapshot,
)
from app.pressure_field import build_pressure_update
from app.processing import SensorDataProcessor
from app.sensor_batch import LiveEligibility, SensorBatch

logger = logging.getLogger(__name__)


class LiveFrameSink(Protocol):
    """Consumer-side seam for the transport that accepts Live Frames."""

    def enqueue_broadcast(
        self,
        frame: SensorUpdateWire,
        *,
        budget_started_at: float | None = None,
    ) -> None: ...


class LivePublicationEnvironment(Protocol):
    """Current application-owned collaborators used to publish Live Frames."""

    @property
    def engine(self) -> MonitoringEngine: ...

    @property
    def ws_manager(self) -> LiveFrameSink: ...

    @property
    def processing_lock(self) -> threading.RLock: ...

    @property
    def scene_profile(self) -> BridgeSceneProfile: ...


class LiveTickEnvironment(LivePublicationEnvironment, Protocol):
    """Current application-owned collaborators used to execute a Live Tick."""

    @property
    def simulator(self) -> DataSimulator: ...

    @property
    def processor(self) -> SensorDataProcessor: ...


def capture_live_snapshot(
    engine: MonitoringEngine,
    processing_lock: threading.RLock,
) -> LiveSensorSnapshot:
    """Copy the live-eligible state under the shared mutation boundary."""
    with processing_lock:
        return LiveSensorSnapshot(
            sensors=cast(
                list[SensorReadingWire],
                engine.get_live_snapshot(limit=32),
            ),
            alerts=cast(
                list[AlertSnapshotRecord],
                engine.get_recent_live_alerts(),
            ),
            stats=engine.get_stats(),
            threshold_profile=engine.threshold_profile_summary(),
        )


class SensorUpdatePublisher:
    """Build and enqueue sensor_update payloads through one policy boundary."""

    def __init__(
        self,
        environment: LivePublicationEnvironment,
        *,
        max_frame_age_seconds: float = 0.5,
    ) -> None:
        self._environment = environment
        self.max_frame_age_seconds = max_frame_age_seconds

    def capture_snapshot(self) -> LiveSensorSnapshot:
        environment = self._environment
        return capture_live_snapshot(
            environment.engine,
            environment.processing_lock,
        )

    def _skip_if_stale(self, generated_at: float | None) -> bool:
        if (
            generated_at is None
            or time.monotonic() - generated_at <= self.max_frame_age_seconds
        ):
            return False
        logger.warning("Skipping stale server-generated live frame")
        return True

    def publish(
        self,
        snapshot: LiveSensorSnapshot | None = None,
        *,
        generated_at: float | None = None,
    ) -> bool:
        try:
            if self._skip_if_stale(generated_at):
                return False
            current_snapshot = snapshot or self.capture_snapshot()
            pressure_payload = None
            pressure_omission = None
            try:
                profile = getattr(
                    self._environment,
                    "scene_profile",
                    bundled_scene_profile(),
                )
                pressure_payload = build_pressure_update(
                    current_snapshot.sensors,
                    self._environment.engine.projection_thresholds_for,
                    deck_bounds=profile.deck_bounds.to_dict(),
                    sensor_anchors={
                        sensor_id: anchor.position
                        for sensor_id, anchor in profile.sensor_anchors.items()
                    },
                    generated_at=time.time(),
                )
            except Exception:
                logger.exception("Failed to build pressure_update")
                pressure_omission = "pressure.failed"
            payload = build_sensor_update_from_snapshot(
                current_snapshot,
                pressure=pressure_payload,
                pressure_omission=pressure_omission,
            )
            if self._skip_if_stale(generated_at):
                return False
            self._environment.ws_manager.enqueue_broadcast(
                payload,
                budget_started_at=generated_at,
            )
            return True
        except Exception:
            logger.exception("Failed to publish sensor_update; continuing live stream")
            return False


class LiveTickPipeline:
    """Generate, ingest, snapshot, and publish one serialized Live Tick."""

    def __init__(
        self,
        *,
        environment: LiveTickEnvironment,
        max_frame_age_seconds: float = 0.5,
    ) -> None:
        self._environment = environment
        self._publisher = SensorUpdatePublisher(
            environment,
            max_frame_age_seconds=max_frame_age_seconds,
        )

    def run_once(self, generated_at: float) -> None:
        environment = self._environment
        try:
            raw_readings = environment.simulator.next_readings()
        except Exception:
            logger.exception("Live simulator generation failed")
            raw_readings = []

        readings = validate_live_json_records(raw_readings)
        with environment.processing_lock:
            pending_external = environment.engine.get_pending_external_versions()
            readings = [
                reading
                for reading in readings
                if str(reading["sensor_id"]) not in pending_external
            ]
            batch = SensorBatch(
                records=readings,
                live_eligibility=LiveEligibility.INTERNAL,
            )
            try:
                environment.processor.process(batch)
            except Exception:
                logger.exception("Live ingestion/detector pipeline failed")
            snapshot = self._publisher.capture_snapshot()

        published = self._publisher.publish(snapshot, generated_at=generated_at)
        if published:
            with environment.processing_lock:
                environment.engine.consume_pending_external(pending_external)


class LiveStreamRunner:
    """Own the one application-scoped live stream thread."""

    def __init__(
        self,
        process_tick: Callable[[float], None],
        interval_seconds: Callable[[], float],
        set_running: Callable[[bool], None],
    ) -> None:
        self._process_tick = process_tick
        self._interval_seconds = interval_seconds
        self._set_running = set_running
        self._lifecycle_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def is_running(self) -> bool:
        thread = self._thread
        return thread is not None and thread.is_alive()

    def start(self) -> None:
        with self._lifecycle_lock:
            thread = self._thread
            if (
                thread is not None
                and thread.is_alive()
                and not self._stop_event.is_set()
            ):
                return

        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)

        with self._lifecycle_lock:
            thread = self._thread
            if thread is not None and thread.is_alive():
                logger.error("Live stream did not stop before a restart was requested")
                return

            self._stop_event.clear()
            thread = threading.Thread(
                target=self._run,
                name="bridge-live-stream",
                daemon=True,
            )
            self._thread = thread
            thread.start()

    def stop(self) -> None:
        with self._lifecycle_lock:
            self._stop_event.set()
            thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2.0)

    def _run(self) -> None:
        self._set_running(True)
        next_tick = time.monotonic()
        try:
            while not self._stop_event.is_set():
                generated_at = time.monotonic()
                try:
                    self._process_tick(generated_at)
                except Exception:
                    logger.exception("Live tick failed; continuing with next frame")

                interval = max(float(self._interval_seconds()), 0.001)
                next_tick += interval
                now = time.monotonic()
                if next_tick <= now:
                    next_tick = now + interval
                self._stop_event.wait(next_tick - now)
        finally:
            self._set_running(False)
            with self._lifecycle_lock:
                if self._thread is threading.current_thread():
                    self._thread = None
