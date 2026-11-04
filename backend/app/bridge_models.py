"""Validated storage for imported bridge model files."""

from __future__ import annotations

import io
import json
import logging
import os
import shutil
import struct
import tempfile
import threading
import uuid
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, BinaryIO, Mapping

from app.bridge_scene_profile import (
    BridgeSceneProfile,
    BridgeSceneProfileError,
    infer_scene_profile,
    profile_document_for_model,
)

logger = logging.getLogger(__name__)

MODEL_INDEX_SCHEMA_VERSION = 1
DEFAULT_MAX_MODEL_BYTES = 100 * 1024 * 1024
MODEL_IMPORT_CHUNK_BYTES = 1024 * 1024
SUPPORTED_MODEL_FORMATS = {".glb": "glb", ".gltf": "gltf"}
_MODEL_MEDIA_TYPES = {
    "glb": "model/gltf-binary",
    "gltf": "model/gltf+json",
}


class BridgeModelError(ValueError):
    """An imported bridge model is invalid or cannot be stored safely."""


class BridgeModelTooLargeError(BridgeModelError):
    """An imported bridge model exceeds the configured size limit."""


class BridgeModelNotFoundError(LookupError):
    """No imported bridge model exists for the requested identifier."""


@dataclass(frozen=True, slots=True)
class BridgeModelRecord:
    model_id: str
    name: str
    format: str
    size_bytes: int
    original_filename: str
    created_at: str
    file_name: str
    profile_revision: int = 1
    profile_source: str = "inferred"

    def to_public(self, *, active: bool) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "name": self.name,
            "format": self.format,
            "size_bytes": self.size_bytes,
            "original_filename": self.original_filename,
            "created_at": self.created_at,
            "active": active,
            "file_url": f"/api/models/{self.model_id}/file",
            "media_type": _MODEL_MEDIA_TYPES[self.format],
            "profile_revision": self.profile_revision,
            "profile_source": self.profile_source,
            "profile_url": f"/api/models/{self.model_id}/profile",
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> BridgeModelRecord:
        return cls(
            model_id=str(value["model_id"]),
            name=str(value["name"]),
            format=str(value["format"]),
            size_bytes=int(value["size_bytes"]),
            original_filename=str(value["original_filename"]),
            created_at=str(value["created_at"]),
            file_name=str(value["file_name"]),
            profile_revision=int(value.get("profile_revision", 1)),
            profile_source=str(value.get("profile_source", "inferred")),
        )


class BridgeModelStore:
    """Persist imported models and the single active model selection."""

    def __init__(
        self,
        root: str | Path,
        *,
        max_model_bytes: int = DEFAULT_MAX_MODEL_BYTES,
    ) -> None:
        self.root = Path(root)
        self.index_path = self.root / "index.json"
        self.max_model_bytes = max_model_bytes
        self._lock = threading.RLock()
        self._records: dict[str, BridgeModelRecord] = {}
        self._active_id: str | None = None
        self._load_index()

    def list_models(self) -> list[dict[str, Any]]:
        with self._lock:
            records = sorted(
                self._records.values(),
                key=lambda record: record.created_at,
                reverse=True,
            )
            return [
                record.to_public(active=record.model_id == self._active_id)
                for record in records
            ]

    def active_model(self) -> BridgeModelRecord | None:
        with self._lock:
            if self._active_id is None:
                return None
            return self._records.get(self._active_id)

    def get(self, model_id: str) -> BridgeModelRecord:
        with self._lock:
            record = self._records.get(model_id)
        if record is None:
            raise BridgeModelNotFoundError(f"Bridge model {model_id!r} not found")
        return record

    def import_file(
        self,
        source: str | Path,
        original_filename: str,
        *,
        display_name: str | None = None,
        activate: bool = True,
        profile_document: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            with Path(source).open("rb") as stream:
                return self.import_stream(
                    stream,
                    original_filename,
                    display_name=display_name,
                    activate=activate,
                    profile_document=profile_document,
                )
        except OSError as exc:
            raise BridgeModelError(f"Cannot read bridge model: {exc}") from exc

    def import_stream(
        self,
        stream: BinaryIO,
        original_filename: str,
        *,
        display_name: str | None = None,
        activate: bool = True,
        profile_document: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Validate and store one model from an owned byte stream."""
        clean_filename = Path(original_filename).name
        suffix = Path(clean_filename).suffix.lower()
        model_format = SUPPORTED_MODEL_FORMATS.get(suffix)
        if model_format is None:
            raise BridgeModelError("Only .glb and .gltf bridge models are supported")
        self.root.mkdir(parents=True, exist_ok=True)
        model_id = uuid.uuid4().hex
        model_dir = self.root / model_id
        target_name = f"model{suffix}"
        created_at = datetime.now(UTC).isoformat()
        resolved_name = (display_name or Path(clean_filename).stem or "Imported bridge").strip()
        if not resolved_name:
            resolved_name = "Imported bridge"
        temporary_name: str | None = None
        model_dir_created = False
        try:
            with tempfile.NamedTemporaryFile(
                dir=self.root,
                prefix=".upload-",
                delete=False,
            ) as temporary:
                temporary_name = temporary.name
                size_bytes = 0
                while True:
                    chunk = stream.read(MODEL_IMPORT_CHUNK_BYTES)
                    if not chunk:
                        break
                    if not isinstance(chunk, (bytes, bytearray, memoryview)):
                        raise BridgeModelError(
                            "Bridge model stream must contain bytes"
                        )
                    size_bytes += len(chunk)
                    if size_bytes > self.max_model_bytes:
                        raise BridgeModelTooLargeError(
                            f"Bridge model exceeds {self.max_model_bytes} bytes"
                        )
                    temporary.write(chunk)
                if size_bytes <= 0:
                    raise BridgeModelError("Bridge model file is empty")
                temporary.flush()
                os.fsync(temporary.fileno())

            staged_path = Path(temporary_name)
            self._validate_model(staged_path, model_format)
            model_dir.mkdir(parents=True, exist_ok=False)
            model_dir_created = True
            target_path = model_dir / target_name
            os.replace(staged_path, target_path)
            temporary_name = None
            profile = self._create_initial_profile(
                model_id,
                target_path,
                resolved_name,
                profile_document,
            )
            self._persist_profile(model_id, profile)
            record = BridgeModelRecord(
                model_id=model_id,
                name=resolved_name[:120],
                format=model_format,
                size_bytes=size_bytes,
                original_filename=clean_filename,
                created_at=created_at,
                file_name=target_name,
            )
            record = replace(
                record,
                profile_revision=profile.revision,
                profile_source=profile.source,
            )
            with self._lock:
                self._records[model_id] = record
                if activate:
                    self._active_id = model_id
                self._write_index_locked()
                is_active = self._active_id == model_id
        except Exception as exc:
            if model_dir_created:
                shutil.rmtree(model_dir, ignore_errors=True)
            with self._lock:
                self._records.pop(model_id, None)
                if self._active_id == model_id:
                    self._active_id = None
            if isinstance(exc, OSError):
                raise BridgeModelError(
                    f"Cannot store bridge model: {exc}"
                ) from exc
            raise
        finally:
            if temporary_name is not None:
                Path(temporary_name).unlink(missing_ok=True)
        return record.to_public(active=is_active)

    def import_bytes(
        self,
        content: bytes,
        original_filename: str,
        *,
        display_name: str | None = None,
        activate: bool = True,
        profile_document: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.import_stream(
            io.BytesIO(content),
            original_filename,
            display_name=display_name,
            activate=activate,
            profile_document=profile_document,
        )

    def activate(self, model_id: str) -> dict[str, Any]:
        with self._lock:
            record = self._records.get(model_id)
            if record is None:
                raise BridgeModelNotFoundError(
                    f"Bridge model {model_id!r} not found"
                )
            self._active_id = model_id
            self._write_index_locked()
            return record.to_public(active=True)

    def deactivate(self) -> None:
        with self._lock:
            self._active_id = None
            self._write_index_locked()

    def replace_profile(
        self,
        model_id: str,
        document: Mapping[str, Any],
    ) -> dict[str, Any]:
        with self._lock:
            record = self._records.get(model_id)
            if record is None:
                raise BridgeModelNotFoundError(
                    f"Bridge model {model_id!r} not found"
                )
            revision = record.profile_revision + 1
            profile = profile_document_for_model(
                document,
                profile_id=model_id,
                revision=revision,
            )
            self._persist_profile(model_id, profile)
            updated = replace(
                record,
                profile_revision=profile.revision,
                profile_source=profile.source,
            )
            self._records[model_id] = updated
            self._write_index_locked()
            return updated.to_public(active=model_id == self._active_id)

    def load_profile(
        self,
        model_id: str,
        revision: int | None = None,
    ) -> BridgeSceneProfile:
        with self._lock:
            record = self._records.get(model_id)
            if record is None:
                raise BridgeModelNotFoundError(
                    f"Bridge model {model_id!r} not found"
                )
            selected_revision = record.profile_revision if revision is None else revision
            path = self._profile_path(model_id, selected_revision)
            if path.is_file():
                return BridgeSceneProfile.load(path)
            if revision is not None or record.profile_source == "explicit":
                raise BridgeSceneProfileError(
                    f"Scene profile revision {selected_revision} is missing"
                )
            model_path = self.root / record.model_id / record.file_name
            if not model_path.is_file():
                raise BridgeModelNotFoundError(
                    f"Bridge model file for {model_id!r} is missing"
                )
            profile = infer_scene_profile(
                model_path,
                profile_id=model_id,
                revision=max(record.profile_revision, 1),
                display={"name": record.name},
            )
            self._persist_profile(model_id, profile)
            updated = replace(
                record,
                profile_revision=profile.revision,
                profile_source=profile.source,
            )
            self._records[model_id] = updated
            self._write_index_locked()
            return profile

    def active_profile(self) -> BridgeSceneProfile | None:
        with self._lock:
            record = self._records.get(self._active_id) if self._active_id else None
        if record is None:
            return None
        return self.load_profile(record.model_id)

    def profile_public(self, model_id: str, revision: int | None = None) -> dict[str, Any]:
        return self.load_profile(model_id, revision).to_dict()

    def delete(self, model_id: str) -> None:
        with self._lock:
            record = self._records.get(model_id)
            if record is None:
                raise BridgeModelNotFoundError(
                    f"Bridge model {model_id!r} not found"
                )
            model_dir = self.root / record.model_id
            if model_dir.parent.resolve() != self.root.resolve():
                raise BridgeModelError("Refusing to delete outside the model directory")
            self._records.pop(model_id, None)
            if self._active_id == model_id:
                self._active_id = None
            self._write_index_locked()
        shutil.rmtree(model_dir, ignore_errors=True)

    def file_path(self, model_id: str) -> Path:
        record = self.get(model_id)
        path = self.root / record.model_id / record.file_name
        if path.parent.resolve() != (self.root / record.model_id).resolve():
            raise BridgeModelError("Bridge model path escaped its storage directory")
        if not path.is_file():
            raise BridgeModelNotFoundError(f"Bridge model file for {model_id!r} is missing")
        return path

    def _profile_path(self, model_id: str, revision: int) -> Path:
        return self.root / model_id / "profiles" / f"profile-{revision:04d}.json"

    def _persist_profile(self, model_id: str, profile: BridgeSceneProfile) -> None:
        profile.save(self._profile_path(model_id, profile.revision))

    def _create_initial_profile(
        self,
        model_id: str,
        model_path: Path,
        display_name: str,
        document: Mapping[str, Any] | None,
    ) -> BridgeSceneProfile:
        if document is not None:
            return profile_document_for_model(
                document,
                profile_id=model_id,
                revision=1,
            )
        return infer_scene_profile(
            model_path,
            profile_id=model_id,
            revision=1,
            display={"name": display_name},
        )

    def _validate_model(self, path: Path, model_format: str) -> None:
        if model_format == "glb":
            self._validate_glb(path)
        else:
            self._validate_gltf(path)

    def _validate_glb(self, path: Path) -> None:
        try:
            with path.open("rb") as handle:
                header = handle.read(12)
                if len(header) != 12:
                    raise BridgeModelError("GLB header is incomplete")
                magic, version, declared_length = struct.unpack("<4sII", header)
                if magic != b"glTF":
                    raise BridgeModelError("File does not contain a GLB header")
                if version != 2:
                    raise BridgeModelError("Only glTF 2.0 GLB files are supported")
                if declared_length != path.stat().st_size:
                    raise BridgeModelError("GLB declared length does not match the file size")
                chunk_header = handle.read(8)
                if len(chunk_header) != 8:
                    raise BridgeModelError("GLB JSON chunk is missing")
                chunk_length, chunk_type = struct.unpack("<II", chunk_header)
                if chunk_type != 0x4E4F534A:
                    raise BridgeModelError("GLB first chunk must be JSON")
                payload = handle.read(chunk_length)
        except OSError as exc:
            raise BridgeModelError(f"Cannot read GLB model: {exc}") from exc
        self._validate_gltf_json(payload)

    def _validate_gltf(self, path: Path) -> None:
        try:
            payload = path.read_bytes()
        except OSError as exc:
            raise BridgeModelError(f"Cannot read glTF model: {exc}") from exc
        self._validate_gltf_json(payload)

    @staticmethod
    def _validate_gltf_json(payload: bytes) -> None:
        try:
            document = json.loads(payload.decode("utf-8").rstrip("\x00 "))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BridgeModelError("Bridge model contains invalid glTF JSON") from exc
        if not isinstance(document, Mapping):
            raise BridgeModelError("glTF document must be a JSON object")
        asset = document.get("asset")
        if not isinstance(asset, Mapping) or str(asset.get("version", "")) != "2.0":
            raise BridgeModelError("Only glTF asset version 2.0 is supported")
        for collection_name in ("buffers", "images"):
            collection = document.get(collection_name, [])
            if collection is None:
                continue
            if not isinstance(collection, list):
                raise BridgeModelError(f"glTF {collection_name} must be an array")
            for item in collection:
                if not isinstance(item, Mapping):
                    raise BridgeModelError(f"glTF {collection_name} entry is invalid")
                uri = item.get("uri")
                if isinstance(uri, str) and not uri.startswith("data:"):
                    raise BridgeModelError(
                        "External glTF resources are not supported; export a .glb "
                        "or a self-contained .gltf"
                    )

    def _load_index(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            raw = self.index_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return
        except (OSError, UnicodeError) as exc:
            logger.warning("Cannot read bridge model index: %s", exc)
            return
        try:
            document = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.warning("Bridge model index is not valid JSON: %s", exc)
            return
        if not isinstance(document, Mapping):
            logger.warning("Bridge model index must contain an object")
            return
        if document.get("schema_version") != MODEL_INDEX_SCHEMA_VERSION:
            logger.warning("Bridge model index has an unsupported schema version")
            return
        models = document.get("models", [])
        if not isinstance(models, list):
            logger.warning("Bridge model index models must be an array")
            return
        records: dict[str, BridgeModelRecord] = {}
        for entry in models:
            if not isinstance(entry, Mapping):
                continue
            try:
                record = BridgeModelRecord.from_dict(entry)
            except (KeyError, TypeError, ValueError):
                continue
            if not (self.root / record.model_id / record.file_name).is_file():
                continue
            records[record.model_id] = record
        active_id = document.get("active_id")
        self._records = records
        self._active_id = str(active_id) if active_id in records else None

    def _write_index_locked(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        document = {
            "schema_version": MODEL_INDEX_SCHEMA_VERSION,
            "active_id": self._active_id,
            "models": [
                {
                    "model_id": record.model_id,
                    "name": record.name,
                    "format": record.format,
                    "size_bytes": record.size_bytes,
                    "original_filename": record.original_filename,
                    "created_at": record.created_at,
                    "file_name": record.file_name,
                    "profile_revision": record.profile_revision,
                    "profile_source": record.profile_source,
                }
                for record in sorted(
                    self._records.values(),
                    key=lambda item: item.created_at,
                )
            ],
        }
        encoded = json.dumps(document, ensure_ascii=False, indent=2).encode("utf-8")
        temporary_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=self.root,
                prefix=".index-",
                delete=False,
            ) as temporary:
                temporary.write(encoded)
                temporary.flush()
                os.fsync(temporary.fileno())
                temporary_name = temporary.name
            os.replace(temporary_name, self.index_path)
        finally:
            if temporary_name is not None:
                Path(temporary_name).unlink(missing_ok=True)
