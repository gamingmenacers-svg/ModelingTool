from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image


@dataclass
class MaterialInspection:
    material_name: str
    source_slots: dict[str, dict[str, Any]]
    metallic_factor: float
    roughness_factor: float
    authored_alpha_mode: str
    meaningful_alpha: bool
    assumptions: list[str] = field(default_factory=list)

    def summary(self) -> str:
        labels = {
            "albedo": "base colour",
            "normal": "normal",
            "metallic_roughness": "metal/rough",
            "occlusion": "AO",
            "emissive": "emissive",
        }
        detected = [
            f"{labels[key]} {value['width']}×{value['height']}"
            for key, value in self.source_slots.items()
            if value.get("present")
        ]
        missing = [labels[key] for key, value in self.source_slots.items() if not value.get("present")]
        alpha = "meaningful alpha" if self.meaningful_alpha else "opaque alpha"
        first = " • ".join(detected) if detected else "No image maps"
        return f"{first} • {alpha}" + (f" • missing: {', '.join(missing)}" if missing else "")


@dataclass
class MaterialCompileResult:
    asset_name: str
    shader: str
    inspection: MaterialInspection
    outputs: dict[str, Path]
    manifest_path: Path
    packed_specular_uses_source_maps: bool

    def to_dict(self) -> dict[str, Any]:
        data = {
            "asset_name": self.asset_name,
            "shader": self.shader,
            "inspection": asdict(self.inspection),
            "outputs": {name: str(path) for name, path in self.outputs.items()},
            "packed_specular_uses_source_maps": self.packed_specular_uses_source_maps,
        }
        return data


def _image(value: object) -> Image.Image | None:
    if value is not None and hasattr(value, "convert") and hasattr(value, "size"):
        return value  # type: ignore[return-value]
    return None


def _material_texture(material: object | None, *names: str) -> Image.Image | None:
    if material is None:
        return None
    for name in names:
        image = _image(getattr(material, name, None))
        if image is not None:
            return image
    return None


def _factor(material: object | None, name: str, default: float) -> float:
    value = getattr(material, name, None) if material is not None else None
    try:
        return float(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def inspect_source_material(mesh) -> MaterialInspection:
    material = getattr(getattr(mesh, "visual", None), "material", None)
    images = {
        "albedo": _material_texture(material, "baseColorTexture", "image"),
        "normal": _material_texture(material, "normalTexture"),
        "metallic_roughness": _material_texture(material, "metallicRoughnessTexture"),
        "occlusion": _material_texture(material, "occlusionTexture"),
        "emissive": _material_texture(material, "emissiveTexture"),
    }
    slots = {
        name: {
            "present": image is not None,
            "width": int(image.size[0]) if image is not None else None,
            "height": int(image.size[1]) if image is not None else None,
            "mode": str(image.mode) if image is not None else None,
            "filename": str(getattr(image, "filename", "") or "") if image is not None else None,
        }
        for name, image in images.items()
    }
    albedo = images["albedo"]
    meaningful_alpha = False
    if albedo is not None and "A" in albedo.getbands():
        minimum, maximum = albedo.getchannel("A").getextrema()
        meaningful_alpha = bool(minimum < 255 or maximum < 255)
    authored_alpha = str(getattr(material, "alphaMode", "OPAQUE") or "OPAQUE").upper()
    assumptions: list[str] = []
    metallic = _factor(material, "metallicFactor", 0.0)
    roughness = _factor(material, "roughnessFactor", 0.5)
    if images["metallic_roughness"] is None:
        assumptions.append(f"No metallic/roughness image was supplied; using metallic {metallic:.3f} and roughness {roughness:.3f}.")
    if images["occlusion"] is None:
        assumptions.append("No ambient-occlusion map was supplied; using white AO.")
    if authored_alpha != "OPAQUE" and not meaningful_alpha:
        assumptions.append(f"The source tagged alpha as {authored_alpha}, but every albedo alpha pixel is opaque; recommending OPAQUE.")
    return MaterialInspection(
        material_name=str(getattr(material, "name", "") or "unnamed_material"),
        source_slots=slots,
        metallic_factor=max(0.0, min(1.0, metallic)),
        roughness_factor=max(0.0, min(1.0, roughness)),
        authored_alpha_mode=authored_alpha,
        meaningful_alpha=meaningful_alpha,
        assumptions=assumptions,
    )


def _resized_channel(image: Image.Image | None, channel: str, size: tuple[int, int], default: int) -> Image.Image:
    if image is None:
        return Image.new("L", size, color=max(0, min(255, default)))
    converted = image.convert("RGBA")
    band = converted.getchannel(channel)
    if band.size != size:
        band = band.resize(size, Image.Resampling.LANCZOS)
    return band


def compile_bannerlord_material(mesh, output_dir: Path, asset_name: str) -> MaterialCompileResult:
    """Extract source maps and build Bannerlord's documented metallic PBR inputs."""

    output_dir.mkdir(parents=True, exist_ok=True)
    inspection = inspect_source_material(mesh)
    material = getattr(getattr(mesh, "visual", None), "material", None)
    albedo = _material_texture(material, "baseColorTexture", "image")
    normal = _material_texture(material, "normalTexture")
    metallic_roughness = _material_texture(material, "metallicRoughnessTexture")
    occlusion = _material_texture(material, "occlusionTexture")
    emissive = _material_texture(material, "emissiveTexture")
    available = [image for image in (metallic_roughness, occlusion, albedo) if image is not None]
    size = max((image.size for image in available), key=lambda value: value[0] * value[1], default=(4, 4))

    outputs: dict[str, Path] = {}
    if albedo is not None:
        albedo_path = output_dir / f"{asset_name}_d.png"
        mode = "RGBA" if inspection.meaningful_alpha else "RGB"
        albedo.convert(mode).save(albedo_path, format="PNG", optimize=True)
        outputs["albedo"] = albedo_path
    if normal is not None:
        normal_path = output_dir / f"{asset_name}_n.png"
        normal.convert("RGB").save(normal_path, format="PNG", optimize=True)
        outputs["normal"] = normal_path
    if emissive is not None:
        emissive_path = output_dir / f"{asset_name}_emissive.png"
        emissive.convert("RGB").save(emissive_path, format="PNG", optimize=True)
        outputs["emissive"] = emissive_path

    metallic_default = round(inspection.metallic_factor * 255)
    roughness_default = round(inspection.roughness_factor * 255)
    metallic = _resized_channel(metallic_roughness, "B", size, metallic_default)
    roughness = _resized_channel(metallic_roughness, "G", size, roughness_default)
    glossiness = roughness.point(lambda value: 255 - value)
    ambient_occlusion = _resized_channel(occlusion, "R", size, 255)
    packed = Image.merge("RGBA", (metallic, glossiness, ambient_occlusion, Image.new("L", size, 255)))
    specular_path = output_dir / f"{asset_name}_s.png"
    packed.save(specular_path, format="PNG", optimize=True)
    outputs["packed_specular"] = specular_path

    recommended_alpha = "ALPHA_BLEND" if inspection.meaningful_alpha else "OPAQUE"
    payload = {
        "schema": 1,
        "asset_name": asset_name,
        "shader": "pbr_metallic",
        "source_material": asdict(inspection),
        "outputs": {name: str(path) for name, path in outputs.items()},
        "bannerlord_mapping": {
            "diffuse_1": str(outputs.get("albedo", "")),
            "normal": str(outputs.get("normal", "")),
            "specular": str(specular_path),
            "specular_channels": {
                "red": "metallic",
                "green": "glossiness (1 - roughness)",
                "blue": "ambient occlusion",
                "alpha": "255; no translucency authored by this compiler",
            },
            "recommended_alpha_mode": recommended_alpha,
            "vertex_layout": {"bump_map": normal is not None, "skinning_set_by_equipment_slot": True},
        },
        "source_modified": False,
    }
    manifest_path = output_dir / f"{asset_name}_material.json"
    manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return MaterialCompileResult(
        asset_name=asset_name,
        shader="pbr_metallic",
        inspection=inspection,
        outputs=outputs,
        manifest_path=manifest_path,
        packed_specular_uses_source_maps=bool(metallic_roughness is not None or occlusion is not None),
    )
