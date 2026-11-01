"""Atomic checkpoint persistence for application monitoring state."""

from __future__ import annotations

import json
import logging
import math
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Mapping, Protocol

from app.engine.data_engine import MonitoringEngine

logger = logging.getLogger(__name__)

CHECKPOINT_SCHEMA_VERSION = 1
DEFAULT_CHECKPOINT_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "state" / "monitoring.json"
)


class CheckpointError(RuntimeError):
    """A checkpoint cannot be read or written safely."""


class CheckpointStore(Protocol):
    """Replaceable persistence boundary for one complete monitoring checkpoint."""

    def load(self) -> dict[str, Any] | None:
        """Return the last complete checkpoint, or None when no checkpoint exists."""

    def save(self, payload: Mapping[str, Any]) -> None:
        """Atomically replace the current checkpoint."""


class JsonCheckpointStore:
    """Store checkpoints as one atomically replaced UTF-8 JSON document."""

    def __init__(self, path: str | Path = DEFAULT_CHECKPOINT_PATH) -> None:
        self.path = Path(path)

    def load(self) -> dict[str, Any] | None:
        try:
            raw = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except (OSError, UnicodeError) as exc:
            raise CheckpointError(f"cannot read checkpoint {self.path}: {exc}") from exc

        if not raw.strip():
            raise CheckpointError(f"checkpoint {self.path} is empty")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise CheckpointError(
                f"checkpoint {self.path} is not valid JSON: {exc.msg}"
            ) from exc
        if not isinstance(payload, dict):
            raise CheckpointError(f"checkpoint {self.path} must contain an object")
        if payload.get("schema_version") != CHECKPOINT_SCHEMA_VERSION:
            raise CheckpointError(
                f"checkpoint {self.path} has unsupported schema_version"
            )
        if not isinstance(payload.get("state"), dict):
            raise CheckpointError(f"checkpoint {self.path} has no state object")
        return payload

    def save(self, payload: Mapping[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            encoded = json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise CheckpointError(
                f"checkpoint is not JSON serializable: {exc}"
            ) from exc

        descriptor, temporary_name = tempfile.mkstemp(
            dir=self.path.parent,
            prefix=f".{self.path.name}.",
            suffix=".tmp",
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, self.path)
            self._sync_parent_directory()
        except BaseException:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise

    def _sync_parent_directory(self) -> None:
        """Best-effort directory sync after the atomic rename."""
        try:
            descriptor = os.open(self.path.parent, os.O_RDONLY)
        except (AttributeError, OSError):
            return
        try:
            os.fsync(descriptor)
        except OSError:
            pass
        finally:
            os.close(descriptor)


class CheckpointManager:
    """Restore and commit engine state without leaking storage details inward."""

    def __init__(
        self,
        engine: MonitoringEngine,
        store: CheckpointStore,
    ) -> None:
        self.engine = engine
        self.store = store
        self.restored = False
        self.last_saved_at: float | None = None
        self.last_error: str | None = None
        self.commit_count = 0

    def restore(self) -> bool:
        """Restore the newest committed checkpoint, tolerating a damaged file."""
        try:
            payload = self.store.load()
        except Exception as exc:
            self.last_error = str(exc)
            logger.warning("Ignoring unusable monitoring checkpoint: %s", exc)
            return False

        if payload is None:
            return False

        state = payload.get("state")
        if not isinstance(state, dict):
            self.last_error = "checkpoint state must be an object"
            logger.warning("Ignoring monitoring checkpoint: %s", self.last_error)
            return False
        try:
            self.engine.restore_state(state)
        except (KeyError, TypeError, ValueError) as exc:
            self.last_error = f"checkpoint state is invalid: {exc}"
            logger.warning("Ignoring monitoring checkpoint: %s", self.last_error)
            return False

        self.restored = True
        self.last_error = None
        logger.info(
            "Restored monitoring checkpoint with %d sensors and %d alerts",
            self.engine.get_sensor_count(),
            self.engine.get_alert_count(),
        )
        return True

    def commit(self) -> bool:
        """Persist a complete state snapshot while keeping the service available."""
        try:
            state = _json_safe(self.engine.export_state())
            payload = {
                "schema_version": CHECKPOINT_SCHEMA_VERSION,
                "saved_at": time.time(),
                "state": state,
            }
            self.store.save(payload)
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            logger.exception("Failed to persist monitoring checkpoint")
            return False

        self.last_saved_at = float(payload["saved_at"])
        self.last_error = None
        self.commit_count += 1
        return True

    def status(self) -> dict[str, Any]:
        store_path = getattr(self.store, "path", None)
        return {
            "enabled": True,
            "store": type(self.store).__name__,
            "path": str(store_path) if store_path is not None else None,
            "restored": self.restored,
            "last_saved_at": self.last_saved_at,
            "last_error": self.last_error,
            "commit_count": self.commit_count,
        }


def _json_safe(value: Any) -> Any:
    """Normalize detector payloads into portable JSON values."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    item_method = getattr(value, "item", None)
    if callable(item_method):
        try:
            return _json_safe(item_method())
        except (TypeError, ValueError):
            pass
    return str(value)
