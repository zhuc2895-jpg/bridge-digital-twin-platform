"""Versioned spatial profiles for bridge scene interpretation."""

from __future__ import annotations

import json
import math
import re
import struct
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

PROFILE_SCHEMA_VERSION = 1
DEFAULT_SCENE_LENGTH_M = 240.0
_DECK_NAME = re.compile(r"桥面|主梁|箱梁|deck|girder", re.IGNORECASE)
_PROFILE_SOURCES = {"bundled", "explicit", "inferred"}


class BridgeSceneProfileError(ValueError):
    """A scene profile is invalid or cannot be inferred."""


def _finite(value: Any, field_name: str) -> float:
    if isinstance(value, bool):
        raise BridgeSceneProfileError(f"{field_name} must be a number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise BridgeSceneProfileError(f"{field_name} must be a number") from exc
    if not math.isfinite(number):
        raise BridgeSceneProfileError(f"{field_name} must be finite")
    return number


def _triplet(value: Any, field_name: str) -> tuple[float, float, float]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise BridgeSceneProfileError(f"{field_name} must be a three-value array")
    if len(value) != 3:
        raise BridgeSceneProfileError(f"{field_name} must contain three values")
    return tuple(_finite(item, field_name) for item in value)  # type: ignore[return-value]


def _quaternion(value: Any) -> tuple[float, float, float, float]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise BridgeSceneProfileError("rotation must be a quaternion array")
    if len(value) != 4:
        raise BridgeSceneProfileError("rotation must contain four values")
    return tuple(_finite(item, "rotation") for item in value)  # type: ignore[return-value]


@dataclass(frozen=True, slots=True)
class DeckBounds:
    min_x: float
    max_x: float
    min_y: float
    max_y: float
    min_z: float
    max_z: float

    def __post_init__(self) -> None:
        if not self.min_x < self.max_x:
            raise BridgeSceneProfileError("deck bounds require min_x < max_x")
        if not self.min_y < self.max_y:
            raise BridgeSceneProfileError("deck bounds require min_y < max_y")
        if not self.min_z < self.max_z:
            raise BridgeSceneProfileError("deck bounds require min_z < max_z")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> DeckBounds:
        if not isinstance(value, Mapping):
            raise BridgeSceneProfileError("deck_bounds must be an object")
        return cls(
            min_x=_finite(value.get("min_x"), "deck_bounds.min_x"),
            max_x=_finite(value.get("max_x"), "deck_bounds.max_x"),
            min_y=_finite(value.get("min_y"), "deck_bounds.min_y"),
            max_y=_finite(value.get("max_y"), "deck_bounds.max_y"),
            min_z=_finite(value.get("min_z"), "deck_bounds.min_z"),
            max_z=_finite(value.get("max_z"), "deck_bounds.max_z"),
        )

    def to_dict(self) -> dict[str, float]:
        return {
            "min_x": round(self.min_x, 4),
            "max_x": round(self.max_x, 4),
            "min_y": round(self.min_y, 4),
            "max_y": round(self.max_y, 4),
            "min_z": round(self.min_z, 4),
            "max_z": round(self.max_z, 4),
        }

    @property
    def center(self) -> tuple[float, float, float]:
        return (
            (self.min_x + self.max_x) / 2,
            (self.min_y + self.max_y) / 2,
            (self.min_z + self.max_z) / 2,
        )

    @property
    def length_m(self) -> float:
        return self.max_x - self.min_x

    @property
    def width_m(self) -> float:
        return self.max_z - self.min_z


@dataclass(frozen=True, slots=True)
class ModelTransform:
    translation: tuple[float, float, float]
    rotation: tuple[float, float, float, float]
    scale: tuple[float, float, float]
    source_unit_scale: float = 1.0

    def __post_init__(self) -> None:
        if any(component <= 0 for component in self.scale):
            raise BridgeSceneProfileError("model_transform.scale must be positive")
        if self.source_unit_scale <= 0:
            raise BridgeSceneProfileError("source_unit_scale must be positive")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> ModelTransform:
        if not isinstance(value, Mapping):
            raise BridgeSceneProfileError("model_transform must be an object")
        return cls(
            translation=_triplet(value.get("translation", [0.0, 0.0, 0.0]), "model_transform.translation"),
            rotation=_quaternion(value.get("rotation", [0.0, 0.0, 0.0, 1.0])),
            scale=_triplet(value.get("scale", [1.0, 1.0, 1.0]), "model_transform.scale"),
            source_unit_scale=_finite(value.get("source_unit_scale", 1.0), "model_transform.source_unit_scale"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "translation": list(self.translation),
            "rotation": list(self.rotation),
            "scale": list(self.scale),
            "source_unit_scale": self.source_unit_scale,
        }


@dataclass(frozen=True, slots=True)
class SensorAnchor:
    position: tuple[float, float, float]
    role: str | None = None

    @classmethod
    def from_dict(cls, value: Any) -> SensorAnchor:
        if isinstance(value, Mapping):
            position = value.get("position", value.get("anchor"))
            role = value.get("role")
        else:
            position = value
            role = None
        return cls(
            position=_triplet(position, "sensor_anchor.position"),
            role=str(role).strip() if role is not None and str(role).strip() else None,
        )

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"position": list(self.position)}
        if self.role:
            payload["role"] = self.role
        return payload


@dataclass(frozen=True, slots=True)
class BridgeSceneProfile:
    profile_id: str
    revision: int
    source: str
    model_transform: ModelTransform
    deck_bounds: DeckBounds
    sensor_anchors: Mapping[str, SensorAnchor] = field(default_factory=dict)
    measurement_roles: Mapping[str, str] = field(default_factory=dict)
    display: Mapping[str, Any] = field(default_factory=dict)
    schema_version: int = PROFILE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != PROFILE_SCHEMA_VERSION:
            raise BridgeSceneProfileError("unsupported profile schema_version")
        if not str(self.profile_id).strip():
            raise BridgeSceneProfileError("profile_id is required")
        if isinstance(self.revision, bool) or int(self.revision) < 1:
            raise BridgeSceneProfileError("profile revision must be at least one")
        if self.source not in _PROFILE_SOURCES:
            raise BridgeSceneProfileError("profile source is invalid")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "profile_id": self.profile_id,
            "revision": self.revision,
            "source": self.source,
            "coordinate_frame": {
                "handedness": "right",
                "units": "m",
                "up": "Y",
                "longitudinal": "X",
                "transverse": "Z",
            },
            "model_transform": self.model_transform.to_dict(),
            "deck_bounds": self.deck_bounds.to_dict(),
            "sensor_anchors": {
                sensor_id: anchor.to_dict()
                for sensor_id, anchor in sorted(self.sensor_anchors.items())
            },
            "measurement_roles": dict(sorted(self.measurement_roles.items())),
            "display": dict(self.display),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> BridgeSceneProfile:
        if not isinstance(value, Mapping):
            raise BridgeSceneProfileError("scene profile must be an object")
        if value.get("schema_version") != PROFILE_SCHEMA_VERSION:
            raise BridgeSceneProfileError("unsupported profile schema_version")
        anchors = value.get("sensor_anchors", {})
        roles = value.get("measurement_roles", {})
        display = value.get("display", {})
        if not isinstance(anchors, Mapping):
            raise BridgeSceneProfileError("sensor_anchors must be an object")
        if not isinstance(roles, Mapping):
            raise BridgeSceneProfileError("measurement_roles must be an object")
        if not isinstance(display, Mapping):
            raise BridgeSceneProfileError("display must be an object")
        return cls(
            profile_id=str(value.get("profile_id", "")),
            revision=int(value.get("revision", 1)),
            source=str(value.get("source", "explicit")),
            model_transform=ModelTransform.from_dict(value.get("model_transform", {})),
            deck_bounds=DeckBounds.from_dict(value.get("deck_bounds", {})),
            sensor_anchors={
                str(sensor_id): SensorAnchor.from_dict(anchor)
                for sensor_id, anchor in anchors.items()
            },
            measurement_roles={
                str(role): str(sensor_id)
                for role, sensor_id in roles.items()
            },
            display=dict(display),
        )

    @classmethod
    def load(cls, path: str | Path) -> BridgeSceneProfile:
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise BridgeSceneProfileError(f"cannot load scene profile: {exc}") from exc
        return cls.from_dict(payload)

    def save(self, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


@lru_cache(maxsize=1)
def bundled_scene_profile() -> BridgeSceneProfile:
    return BridgeSceneProfile(
        profile_id="bundled-huihe-bridge",
        revision=1,
        source="bundled",
        model_transform=ModelTransform(
            translation=(0.0, 3.497, 0.0),
            rotation=(0.0, 0.0, 0.0, 1.0),
            scale=(0.003278109, 0.003278109, 0.003278109),
        ),
        deck_bounds=DeckBounds(
            min_x=-119.8,
            max_x=119.8,
            min_y=20.98,
            max_y=23.48,
            min_z=-7.0,
            max_z=7.0,
        ),
        sensor_anchors={
            "S01": SensorAnchor((0.0, 24.2, 0.0), "primary_strain"),
            "S02": SensorAnchor((-30.0, 24.2, 0.0), "quarter_span_strain"),
            "S03": SensorAnchor((60.0, 68.8, 3.0), "tower_displacement"),
            "S04": SensorAnchor((-45.0, 40.0, -3.0), "cable_acceleration"),
            "S05": SensorAnchor((0.0, 24.2, 5.0), "midspan_deflection"),
            "S06": SensorAnchor((60.0, 25.0, 3.0), "tower_base_strain"),
            "S07": SensorAnchor((45.0, 40.0, 3.0), "cable_acceleration_2"),
            "S08": SensorAnchor((0.0, 24.2, -6.0), "deck_temperature"),
        },
        measurement_roles={
            "primary_strain": "S01",
            "tower_displacement": "S03",
            "cable_acceleration": "S04",
        },
        display={
            "name_zh": "浍河大桥",
            "name_en": "HUIHE BRIDGE",
            "bridge_type": "CABLE-STAYED",
            "span_m": 240.0,
            "sensor_node_count": 8,
        },
    )


def profile_document_for_model(
    document: Mapping[str, Any],
    *,
    profile_id: str,
    revision: int,
    source: str = "explicit",
) -> BridgeSceneProfile:
    payload = dict(document)
    payload.update(
        {
            "schema_version": PROFILE_SCHEMA_VERSION,
            "profile_id": profile_id,
            "revision": revision,
            "source": source,
        }
    )
    return BridgeSceneProfile.from_dict(payload)


def _gltf_document(path: Path) -> Mapping[str, Any]:
    if path.suffix.lower() == ".glb":
        raw = path.read_bytes()
        if len(raw) < 20:
            raise BridgeSceneProfileError("GLB file is too short")
        magic, _, _ = struct.unpack_from("<4sII", raw, 0)
        if magic != b"glTF":
            raise BridgeSceneProfileError("invalid GLB header")
        chunk_length, chunk_type = struct.unpack_from("<II", raw, 12)
        if chunk_type != 0x4E4F534A:
            raise BridgeSceneProfileError("GLB JSON chunk is missing")
        payload = raw[20 : 20 + chunk_length]
    else:
        payload = path.read_bytes()
    try:
        document = json.loads(payload.decode("utf-8").rstrip("\x00 "))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BridgeSceneProfileError("cannot parse glTF JSON") from exc
    if not isinstance(document, Mapping):
        raise BridgeSceneProfileError("glTF document must be an object")
    return document


def _node_matrix(node: Mapping[str, Any]) -> np.ndarray:
    if "matrix" in node:
        return np.array(node["matrix"], dtype=float).reshape((4, 4), order="F")
    translation = np.array(node.get("translation", [0.0, 0.0, 0.0]), dtype=float)
    scale = np.array(node.get("scale", [1.0, 1.0, 1.0]), dtype=float)
    x, y, z, w = [float(item) for item in node.get("rotation", [0.0, 0.0, 0.0, 1.0])]
    rotation = np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ]
    )
    matrix = np.eye(4)
    matrix[:3, :3] = rotation @ np.diag(scale)
    matrix[:3, 3] = translation
    return matrix


def _geometry_boxes(path: str | Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    document = _gltf_document(Path(path))
    nodes = list(document.get("nodes", []))
    meshes = list(document.get("meshes", []))
    accessors = list(document.get("accessors", []))
    boxes: list[tuple[str, np.ndarray, np.ndarray]] = []

    def walk(node_index: int, parent: np.ndarray) -> None:
        node = nodes[node_index]
        matrix = parent @ _node_matrix(node)
        mesh_index = node.get("mesh")
        if mesh_index is not None and 0 <= int(mesh_index) < len(meshes):
            mesh = meshes[int(mesh_index)]
            node_min: np.ndarray | None = None
            node_max: np.ndarray | None = None
            for primitive in mesh.get("primitives", []):
                accessor_index = primitive.get("attributes", {}).get("POSITION")
                if accessor_index is None:
                    continue
                accessor = accessors[int(accessor_index)]
                if "min" not in accessor or "max" not in accessor:
                    continue
                low = np.array(accessor["min"], dtype=float)
                high = np.array(accessor["max"], dtype=float)
                corners = np.array(
                    [
                        [x, y, z, 1.0]
                        for x in (low[0], high[0])
                        for y in (low[1], high[1])
                        for z in (low[2], high[2])
                    ]
                )
                transformed = (matrix @ corners.T).T[:, :3]
                item_min = transformed.min(axis=0)
                item_max = transformed.max(axis=0)
                node_min = item_min if node_min is None else np.minimum(node_min, item_min)
                node_max = item_max if node_max is None else np.maximum(node_max, item_max)
            if node_min is not None and node_max is not None:
                boxes.append((str(node.get("name", "")), node_min, node_max))
        for child in node.get("children", []):
            walk(int(child), matrix)

    for root in document.get("scenes", [{}])[0].get("nodes", []):
        walk(int(root), np.eye(4))
    if not boxes:
        raise BridgeSceneProfileError("model has no position bounds")
    overall_min = np.min([box[1] for box in boxes], axis=0)
    overall_max = np.max([box[2] for box in boxes], axis=0)
    deck_boxes = [box for box in boxes if _DECK_NAME.search(box[0])]
    if deck_boxes:
        deck_min = np.min([box[1] for box in deck_boxes], axis=0)
        deck_max = np.max([box[2] for box in deck_boxes], axis=0)
    else:
        size = overall_max - overall_min
        deck_min = overall_min.copy()
        deck_max = overall_max.copy()
        deck_min[1] = overall_min[1] + size[1] * 0.27
        deck_max[1] = overall_min[1] + size[1] * 0.34
    return overall_min, overall_max, np.concatenate([deck_min, deck_max])


def _quaternion_y(angle_radians: float) -> tuple[float, float, float, float]:
    return (0.0, math.sin(angle_radians / 2), 0.0, math.cos(angle_radians / 2))


def _rotate(points: np.ndarray, quaternion: Sequence[float]) -> np.ndarray:
    x, y, z, w = quaternion
    rotation = np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ]
    )
    return (rotation @ points.T).T


def infer_scene_profile(
    model_path: str | Path,
    *,
    profile_id: str,
    revision: int = 1,
    target_length_m: float = DEFAULT_SCENE_LENGTH_M,
    display: Mapping[str, Any] | None = None,
) -> BridgeSceneProfile:
    overall_min, overall_max, deck_box = _geometry_boxes(model_path)
    x_span = float(overall_max[0] - overall_min[0])
    z_span = float(overall_max[2] - overall_min[2])
    rotation = _quaternion_y(math.pi / 2) if z_span > x_span else (0.0, 0.0, 0.0, 1.0)
    overall_corners = np.array(
        [
            [x, y, z]
            for x in (overall_min[0], overall_max[0])
            for y in (overall_min[1], overall_max[1])
            for z in (overall_min[2], overall_max[2])
        ]
    )
    rotated_overall = _rotate(overall_corners, rotation)
    rotated_min = rotated_overall.min(axis=0)
    rotated_max = rotated_overall.max(axis=0)
    rotated_length = float(rotated_max[0] - rotated_min[0])
    if rotated_length <= 0:
        raise BridgeSceneProfileError("model longitudinal length is zero")
    scale = float(target_length_m) / rotated_length
    translation = np.array(
        [
            -((rotated_min[0] + rotated_max[0]) / 2) * scale,
            -rotated_min[1] * scale,
            -((rotated_min[2] + rotated_max[2]) / 2) * scale,
        ]
    )
    deck_corners = np.array(
        [
            [x, y, z]
            for x in (deck_box[0], deck_box[3])
            for y in (deck_box[1], deck_box[4])
            for z in (deck_box[2], deck_box[5])
        ]
    )
    transformed_deck = _rotate(deck_corners, rotation) * scale + translation
    deck_min = transformed_deck.min(axis=0)
    deck_max = transformed_deck.max(axis=0)
    deck_bounds = DeckBounds(
        min_x=float(deck_min[0]),
        max_x=float(deck_max[0]),
        min_y=float(deck_min[1]),
        max_y=float(deck_max[1]),
        min_z=float(deck_min[2]),
        max_z=float(deck_max[2]),
    )
    anchors = _inferred_anchors(deck_bounds)
    return BridgeSceneProfile(
        profile_id=profile_id,
        revision=revision,
        source="inferred",
        model_transform=ModelTransform(
            translation=tuple(float(item) for item in translation),  # type: ignore[arg-type]
            rotation=rotation,
            scale=(scale, scale, scale),
        ),
        deck_bounds=deck_bounds,
        sensor_anchors=anchors,
        measurement_roles={
            "primary_strain": "S01",
            "tower_displacement": "S03",
            "cable_acceleration": "S04",
        },
        display={
            "bridge_type": "IMPORTED GLTF",
            "span_m": round(deck_bounds.length_m, 2),
            "sensor_node_count": len(anchors),
            **dict(display or {}),
        },
    )


def _inferred_anchors(deck: DeckBounds) -> dict[str, SensorAnchor]:
    center_x, _, center_z = deck.center
    half_length = deck.length_m / 2
    half_width = deck.width_m / 2
    y = deck.max_y + 1.2
    definitions = {
        "S01": (0.0, 0.0),
        "S02": (-0.25, 0.0),
        "S03": (0.5, 0.0),
        "S04": (-0.375, -0.2),
        "S05": (0.0, 0.25),
        "S06": (0.5, 0.15),
        "S07": (0.375, 0.2),
        "S08": (0.0, -0.35),
    }
    return {
        sensor_id: SensorAnchor(
            (
                center_x + longitudinal * half_length,
                y,
                center_z + transverse * half_width,
            )
        )
        for sensor_id, (longitudinal, transverse) in definitions.items()
    }
