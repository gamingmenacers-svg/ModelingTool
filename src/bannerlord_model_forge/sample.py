from __future__ import annotations

from pathlib import Path

import numpy as np
import trimesh

from .mesh_io import export_mesh


def create_sample(path: Path) -> Path:
    """Create an original, generated training cuirass; no game assets are used."""
    torso = trimesh.creation.icosphere(subdivisions=4, radius=1.0)
    torso.apply_scale((0.48, 0.23, 0.62))
    torso.apply_translation((0.0, 0.0, 1.15))
    waist = trimesh.creation.cylinder(radius=0.32, height=0.34, sections=96)
    waist.apply_scale((1.0, 0.70, 1.0))
    waist.apply_translation((0.0, 0.0, 0.68))
    left = trimesh.creation.icosphere(subdivisions=3, radius=0.24)
    left.apply_scale((1.4, 0.55, 0.55))
    left.apply_translation((-0.48, 0.0, 1.42))
    right = left.copy()
    right.apply_translation((0.96, 0.0, 0.0))
    mesh = trimesh.util.concatenate([torso, waist, left, right])
    mesh.vertices[:, 1] += 0.025 * np.sin(mesh.vertices[:, 0] * 18.0)
    mesh.metadata["source_material_names"] = ["training_steel"]
    mesh.metadata["texture_references"] = []
    export_mesh(mesh, path)
    return path
