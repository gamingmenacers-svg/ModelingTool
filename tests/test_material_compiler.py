from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import trimesh
from PIL import Image
from trimesh.visual.material import PBRMaterial
from trimesh.visual.texture import TextureVisuals

from bannerlord_model_forge.material_compiler import (
    compile_bannerlord_material,
    inspect_source_material,
)


def _textured_mesh(material: PBRMaterial) -> trimesh.Trimesh:
    mesh = trimesh.creation.box()
    uv = np.zeros((len(mesh.vertices), 2), dtype=np.float64)
    mesh.visual = TextureVisuals(uv=uv, material=material)
    return mesh


def _digest(image: Image.Image) -> str:
    return hashlib.sha256(image.tobytes()).hexdigest()


def test_compiler_preserves_source_and_packs_documented_bannerlord_channels(
    tmp_path: Path,
) -> None:
    albedo = Image.new("RGBA", (2, 2), (10, 20, 30, 255))
    normal = Image.new("RGB", (2, 2), (128, 128, 255))
    metallic_roughness = Image.new("RGB", (2, 2), (9, 64, 128))
    occlusion = Image.new("RGB", (2, 2), (32, 200, 200))
    albedo_hash = _digest(albedo)
    material = PBRMaterial(
        name="plate_steel",
        baseColorTexture=albedo,
        normalTexture=normal,
        metallicRoughnessTexture=metallic_roughness,
        occlusionTexture=occlusion,
        alphaMode="BLEND",
    )
    mesh = _textured_mesh(material)

    result = compile_bannerlord_material(mesh, tmp_path / "materials", "plate")

    assert _digest(albedo) == albedo_hash
    assert Image.open(result.outputs["albedo"]).mode == "RGB"
    assert Image.open(result.outputs["normal"]).getpixel((0, 0)) == (128, 128, 255)
    packed = Image.open(result.outputs["packed_specular"]).convert("RGBA")
    assert packed.getpixel((0, 0)) == (128, 191, 32, 255)
    assert result.packed_specular_uses_source_maps is True
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["shader"] == "pbr_metallic"
    assert manifest["bannerlord_mapping"]["recommended_alpha_mode"] == "OPAQUE"
    assert manifest["source_modified"] is False


def test_compiler_preserves_meaningful_alpha(tmp_path: Path) -> None:
    albedo = Image.new("RGBA", (2, 2), (50, 60, 70, 255))
    albedo.putpixel((1, 1), (50, 60, 70, 40))
    mesh = _textured_mesh(PBRMaterial(baseColorTexture=albedo, alphaMode="BLEND"))

    result = compile_bannerlord_material(mesh, tmp_path, "cloth")

    compiled = Image.open(result.outputs["albedo"])
    assert compiled.mode == "RGBA"
    assert compiled.getpixel((1, 1))[3] == 40
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["bannerlord_mapping"]["recommended_alpha_mode"] == "ALPHA_BLEND"


def test_missing_source_maps_are_reported_and_use_conservative_defaults(
    tmp_path: Path,
) -> None:
    mesh = trimesh.creation.box()

    inspection = inspect_source_material(mesh)
    result = compile_bannerlord_material(mesh, tmp_path, "untextured")

    assert inspection.source_slots["albedo"]["present"] is False
    assert "No image maps" in inspection.summary()
    assert set(result.outputs) == {"packed_specular"}
    packed = Image.open(result.outputs["packed_specular"]).convert("RGBA")
    assert packed.size == (4, 4)
    assert packed.getpixel((0, 0)) == (0, 127, 255, 255)
    assert result.packed_specular_uses_source_maps is False
