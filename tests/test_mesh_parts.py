from __future__ import annotations

from pathlib import Path

import numpy as np
import trimesh
from PIL import Image

from bannerlord_model_forge.mesh_io import MeshPart, load_mesh_parts


def test_scene_objects_remain_individually_selectable(tmp_path: Path) -> None:
    scene = trimesh.Scene()
    first = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
    second = trimesh.creation.icosphere(subdivisions=1, radius=0.5)
    scene.add_geometry(first, node_name="Chest plate", geom_name="chest")
    transform = np.eye(4)
    transform[0, 3] = 3.0
    scene.add_geometry(second, node_name="Left pauldron", geom_name="pauldron", transform=transform)
    path = tmp_path / "set.glb"
    path.write_bytes(scene.export(file_type="glb"))

    parts, context = load_mesh_parts(path)

    assert len(parts) == 2
    assert {part.name for part in parts} == {"Chest plate", "Left pauldron"}
    assert max(float(part.mesh.centroid[0]) for part in parts) > 2.5
    assert context["source_geometry_count"] == 2


def test_piece_transform_is_non_destructive_and_exportable() -> None:
    mesh = trimesh.creation.box(extents=(2.0, 1.0, 1.0))
    uv = np.column_stack((np.linspace(0.0, 1.0, len(mesh.vertices)), np.linspace(1.0, 0.0, len(mesh.vertices))))
    material = trimesh.visual.material.PBRMaterial(
        name="armour",
        baseColorTexture=Image.new("RGBA", (4, 4), (60, 70, 80, 255)),
    )
    mesh.visual = trimesh.visual.texture.TextureVisuals(uv=uv, material=material)
    original = np.asarray(mesh.vertices).copy()
    transform = np.eye(4)
    transform[:3, 3] = (3.0, 4.0, 5.0)
    part = MeshPart("Chest", mesh, transform=transform)
    prepared = part.transformed_mesh()

    assert np.allclose(mesh.vertices, original)
    assert np.allclose(prepared.centroid, mesh.centroid + (3.0, 4.0, 5.0))
    assert np.allclose(prepared.visual.uv, uv)
    assert prepared.visual.material.baseColorTexture is not None
