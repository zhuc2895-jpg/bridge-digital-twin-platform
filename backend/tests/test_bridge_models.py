import io
import json
import struct
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app.bridge_models import BridgeModelStore, BridgeModelTooLargeError
from app.dependencies import create_services
from app.main import create_app

from tests.helpers import legacy_test_config


def _glb_document() -> bytes:
    document = {
        "asset": {"version": "2.0", "generator": "bridge-tests"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"name": "bridge deck", "mesh": 0}],
        "meshes": [
            {"primitives": [{"attributes": {"POSITION": 0}}]}
        ],
        "buffers": [{"byteLength": 24}],
        "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": 24}],
        "accessors": [
            {
                "bufferView": 0,
                "componentType": 5126,
                "count": 8,
                "type": "VEC3",
                "min": [0.0, 0.0, 0.0],
                "max": [100.0, 10.0, 20.0],
            }
        ],
    }
    encoded = json.dumps(document, separators=(",", ":")).encode("utf-8")
    encoded += b" " * ((4 - len(encoded) % 4) % 4)
    total_length = 12 + 8 + len(encoded)
    return (
        struct.pack("<4sII", b"glTF", 2, total_length)
        + struct.pack("<II", len(encoded), 0x4E4F534A)
        + encoded
    )


def _client(tmp_path):
    config = replace(
        legacy_test_config(),
        model_dir=tmp_path / "models",
        frontend_dist=tmp_path / "missing-frontend",
    )
    services = create_services(config=config)
    return services, TestClient(create_app(services))


def test_model_import_activate_list_and_download(tmp_path) -> None:
    services, client = _client(tmp_path)
    content = _glb_document()

    with client:
        imported = client.post(
            "/api/models/import",
            files={"file": ("bridge.glb", content, "model/gltf-binary")},
            data={"name": "浍河大桥 BIM", "activate": "true"},
        )

        assert imported.status_code == 201
        model = imported.json()["model"]
        assert model["active"] is True
        assert model["name"] == "浍河大桥 BIM"
        assert model["format"] == "glb"
        assert model["profile_revision"] == 1
        assert model["profile_source"] == "inferred"

        active = client.get("/api/models/active")
        assert active.status_code == 200
        assert active.json()["source"] == "imported"
        assert active.json()["file_url"] == f"/api/models/{model['model_id']}/file"
        assert active.json()["profile_url"] == "/api/models/active/profile"

        listing = client.get("/api/models")
        assert listing.status_code == 200
        assert len(listing.json()["models"]) == 1

        downloaded = client.get(model["file_url"])
        assert downloaded.status_code == 200
        assert downloaded.content == content
        assert downloaded.headers["content-type"].startswith("model/gltf-binary")

        profile = client.get("/api/models/active/profile")
        assert profile.status_code == 200
        assert profile.json()["source"] == "inferred"
        assert profile.json()["deck_bounds"]["max_x"] > profile.json()["deck_bounds"]["min_x"]

    assert services.model_store.active_model() is not None


def test_model_index_survives_store_recreation(tmp_path) -> None:
    store = BridgeModelStore(tmp_path / "models")
    imported = store.import_bytes(_glb_document(), "bridge.glb", display_name="A")

    recreated = BridgeModelStore(tmp_path / "models")

    assert recreated.active_model() is not None
    assert recreated.active_model().model_id == imported["model_id"]
    assert recreated.active_profile() is not None


def test_import_stream_owns_size_limit_and_cleans_staging_file(tmp_path) -> None:
    store = BridgeModelStore(tmp_path / "models", max_model_bytes=32)

    with pytest.raises(BridgeModelTooLargeError):
        store.import_stream(io.BytesIO(_glb_document()), "bridge.glb")

    assert store.list_models() == []
    assert list((tmp_path / "models").glob(".upload-*")) == []


def test_import_stream_reads_incrementally_and_promotes_atomically(tmp_path) -> None:
    class SmallReadStream(io.BytesIO):
        def read(self, size: int | None = -1) -> bytes:
            limit = 7 if size is None or size < 0 else min(size, 7)
            return super().read(limit)

    store = BridgeModelStore(tmp_path / "models")

    model = store.import_stream(
        SmallReadStream(_glb_document()),
        "bridge.glb",
        display_name="Streamed bridge",
    )
    record = store.get(model["model_id"])

    assert model["active"] is True
    assert (store.root / record.model_id / record.file_name).is_file()
    assert list(store.root.glob(".upload-*")) == []


def test_import_route_maps_stream_limit_without_staging_file(tmp_path) -> None:
    services, client = _client(tmp_path)
    services.model_store.max_model_bytes = 32

    with client:
        response = client.post(
            "/api/models/import",
            files={"file": ("bridge.glb", _glb_document(), "model/gltf-binary")},
        )

    assert response.status_code == 413
    assert list((tmp_path / "models").glob(".upload-*")) == []


def test_model_import_accepts_explicit_sidecar_profile(tmp_path) -> None:
    services, client = _client(tmp_path)
    profile_document = {
        "deck_bounds": {
            "min_x": -50.0,
            "max_x": 50.0,
            "min_y": 0.0,
            "max_y": 2.0,
            "min_z": -5.0,
            "max_z": 5.0,
        },
        "sensor_anchors": {
            "S01": {"position": [0.0, 3.0, 0.0], "role": "primary_strain"}
        },
        "measurement_roles": {"primary_strain": "S01"},
        "display": {"bridge_type": "TEST", "span_m": 100.0},
    }

    with client:
        response = client.post(
            "/api/models/import",
            files={
                "file": ("bridge.glb", _glb_document(), "model/gltf-binary"),
                "profile_file": (
                    "bridge-profile.json",
                    json.dumps(profile_document).encode("utf-8"),
                    "application/json",
                ),
            },
            data={"name": "Explicit Profile Bridge", "activate": "true"},
        )
        assert response.status_code == 201
        model = response.json()["model"]
        assert model["profile_source"] == "explicit"
        profile = client.get("/api/models/active/profile").json()

    assert profile["source"] == "explicit"
    assert profile["deck_bounds"]["max_x"] == 50.0
    assert profile["measurement_roles"]["primary_strain"] == "S01"
    assert services.scene_profile.deck_bounds.max_x == 50.0


def test_replace_profile_creates_new_revision(tmp_path) -> None:
    _, client = _client(tmp_path)
    replacement = {
        "deck_bounds": {
            "min_x": -80.0,
            "max_x": 80.0,
            "min_y": 1.0,
            "max_y": 3.0,
            "min_z": -6.0,
            "max_z": 6.0,
        },
        "sensor_anchors": {
            "S01": {"position": [0.0, 4.0, 0.0]}
        },
        "measurement_roles": {},
        "display": {"bridge_type": "REPLACED"},
    }
    with client:
        imported = client.post(
            "/api/models/import",
            files={"file": ("bridge.glb", _glb_document(), "model/gltf-binary")},
        ).json()["model"]
        response = client.post(
            f"/api/models/{imported['model_id']}/profile",
            files={
                "file": (
                    "replacement.json",
                    json.dumps(replacement).encode("utf-8"),
                    "application/json",
                )
            },
        )

    assert response.status_code == 200
    assert response.json()["model"]["profile_revision"] == 2
    assert response.json()["model"]["profile_source"] == "explicit"


def test_external_gltf_resources_are_rejected(tmp_path) -> None:
    _, client = _client(tmp_path)
    document = {
        "asset": {"version": "2.0"},
        "buffers": [{"uri": "bridge.bin", "byteLength": 12}],
    }
    with client:
        response = client.post(
            "/api/models/import",
            files={
                "file": (
                    "bridge.gltf",
                    json.dumps(document).encode("utf-8"),
                    "model/gltf+json",
                )
            },
        )

    assert response.status_code == 400
    assert "self-contained" in response.json()["detail"]


def test_unsupported_model_extension_is_rejected(tmp_path) -> None:
    _, client = _client(tmp_path)
    with client:
        response = client.post(
            "/api/models/import",
            files={"file": ("bridge.obj", b"v 0 0 0\n", "text/plain")},
        )

    assert response.status_code == 400
    assert "Only .glb and .gltf" in response.json()["detail"]


def test_delete_active_model_falls_back_to_bundled(tmp_path) -> None:
    _, client = _client(tmp_path)
    with client:
        imported = client.post(
            "/api/models/import",
            files={"file": ("bridge.glb", _glb_document(), "model/gltf-binary")},
        ).json()["model"]

        deleted = client.delete(f"/api/models/{imported['model_id']}")
        assert deleted.status_code == 200

        active = client.get("/api/models/active").json()
        assert active["active"] is None
        assert active["source"] == "bundled"
        assert active["file_url"] == "/models/huihe_bridge.glb"
