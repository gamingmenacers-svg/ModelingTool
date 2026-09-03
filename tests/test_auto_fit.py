from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import trimesh

from bannerlord_model_forge.auto_fit import auto_fit_to_bannerlord


def write_skeleton(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "bones": [
                    {"name": "root_0", "head": [0.0, 0.0, 0.0], "tail": [0.0, 0.0, 0.2]},
                    {"name": "head_1", "head": [0.0, 0.0, 1.6], "tail": [0.0, 0.0, 1.8]},
                ]
            }
        ),
        encoding="utf-8",
    )
    return path


def test_body_auto_fit_is_reversible_uniform_and_centred_on_rig(tmp_path: Path) -> None:
    skeleton = write_skeleton(tmp_path / "skeleton.json")
    mesh = trimesh.creation.box(extents=(300.0, 850.0, 450.0))
    mesh.apply_transform(trimesh.transformations.rotation_matrix(np.deg2rad(37.0), [1.0, 0.2, 0.0]))
    mesh.apply_translation([1200.0, -400.0, 900.0])
    original = np.asarray(mesh.vertices).copy()

    result = auto_fit_to_bannerlord(mesh, skeleton, "body")
    fitted = mesh.copy()
    fitted.apply_transform(result.transform)

    assert np.allclose(mesh.vertices, original)
    assert np.allclose(result.transform[:3, :3].T @ result.transform[:3, :3], np.eye(3) * result.scale**2, atol=1e-7)
    assert np.linalg.norm(np.asarray(fitted.bounds).mean(axis=0) - np.asarray(result.target_centre)) < 0.04
    assert 0.2 <= result.confidence <= 0.92
    assert result.scale < 0.01


def test_weapon_auto_fit_preserves_size_and_centres_origin(tmp_path: Path) -> None:
    skeleton = write_skeleton(tmp_path / "skeleton.json")
    mesh = trimesh.creation.box(extents=(0.06, 1.2, 0.04))
    mesh.apply_translation([5.0, 2.0, -3.0])

    result = auto_fit_to_bannerlord(mesh, skeleton, "weapon")
    fitted = mesh.copy()
    fitted.apply_transform(result.transform)

    assert result.scale == 1.0
    assert np.allclose(np.asarray(fitted.bounds).mean(axis=0), [0.0, 0.0, 0.0], atol=1e-8)
    assert np.isclose(np.linalg.norm(fitted.extents), np.linalg.norm(mesh.extents))


def test_single_glove_side_placement_changes_target_side(tmp_path: Path) -> None:
    skeleton = write_skeleton(tmp_path / "skeleton.json")
    mesh = trimesh.creation.box(extents=(0.12, 0.10, 0.24))

    left = auto_fit_to_bannerlord(mesh, skeleton, "gloves", "left")
    right = auto_fit_to_bannerlord(mesh, skeleton, "gloves", "right")

    assert left.target_centre[0] < 0.0 < right.target_centre[0]
    assert np.isclose(abs(left.target_centre[0]), abs(right.target_centre[0]))
