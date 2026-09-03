from __future__ import annotations

from pathlib import Path

import numpy as np
import trimesh
from PIL import Image
from trimesh.visual.material import PBRMaterial
from trimesh.visual.texture import TextureVisuals

from bannerlord_model_forge.material_preview import export_material_preview
from bannerlord_model_forge.mesh_io import MeshPart


def _part(alpha: int) -> MeshPart:
    mesh = trimesh.creation.box()
    uv = np.zeros((len(mesh.vertices), 2), dtype=float)
    material = PBRMaterial(
        name="marketplace_material",
        baseColorTexture=Image.new("RGBA", (8, 8), (92, 73, 61, alpha)),
        alphaMode="BLEND",
    )
    mesh.visual = TextureVisuals(uv=uv, material=material)
    return MeshPart("Helmet", mesh)


def test_opaque_atlas_is_rendered_as_opaque_without_mutating_source(tmp_path: Path) -> None:
    part = _part(255)

    output = export_material_preview([part], tmp_path / "helmet.glb")
    scene = trimesh.load(output, force="scene", process=False)
    rendered = next(iter(scene.geometry.values()))

    assert rendered.visual.material.alphaMode == "OPAQUE"
    assert part.mesh.visual.material.alphaMode == "BLEND"


def test_meaningful_transparency_remains_blended(tmp_path: Path) -> None:
    part = _part(96)

    output = export_material_preview([part], tmp_path / "cloth.glb")
    scene = trimesh.load(output, force="scene", process=False)
    rendered = next(iter(scene.geometry.values()))

    assert rendered.visual.material.alphaMode == "BLEND"
