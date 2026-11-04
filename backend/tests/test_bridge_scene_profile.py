from __future__ import annotations

from pathlib import Path

import pytest

from app.bridge_scene_profile import (
    BridgeSceneProfile,
    BridgeSceneProfileError,
    bundled_scene_profile,
    infer_scene_profile,
)

_MODEL = (
    Path(__file__).resolve().parents[2]
    / "frontend"
    / "public"
    / "models"
    / "huihe_bridge.glb"
)


def test_bundled_profile_has_physical_anchors_and_roles() -> None:
    profile = bundled_scene_profile()

    assert profile.source == "bundled"
    assert profile.deck_bounds.length_m == pytest.approx(240.0, abs=0.5)
    assert profile.sensor_anchors["S01"].position[1] > profile.deck_bounds.max_y
    assert profile.measurement_roles["primary_strain"] == "S01"


def test_glb_inference_produces_provisional_profile() -> None:
    profile = infer_scene_profile(
        _MODEL,
        profile_id="inferred-test",
        display={"name": "inferred bridge"},
    )

    assert profile.source == "inferred"
    assert profile.revision == 1
    assert profile.deck_bounds.length_m == pytest.approx(240.0, abs=0.5)
    assert set(profile.sensor_anchors) == {f"S{i:02d}" for i in range(1, 9)}
    assert profile.model_transform.scale[0] > 0
    assert profile.display["bridge_type"] == "IMPORTED GLTF"


def test_profile_round_trips_through_json(tmp_path: Path) -> None:
    profile = bundled_scene_profile()
    path = tmp_path / "profile.json"

    profile.save(path)
    loaded = BridgeSceneProfile.load(path)

    assert loaded.to_dict() == profile.to_dict()


def test_profile_rejects_invalid_deck_bounds() -> None:
    document = bundled_scene_profile().to_dict()
    document["deck_bounds"]["min_x"] = document["deck_bounds"]["max_x"]

    with pytest.raises(BridgeSceneProfileError):
        BridgeSceneProfile.from_dict(document)
