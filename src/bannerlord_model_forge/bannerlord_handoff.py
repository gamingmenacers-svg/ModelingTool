from __future__ import annotations

import json
from pathlib import Path

from .config import Preset
from .models import RiggingResult


def write_bannerlord_handoff(
    output_dir: Path,
    asset_name: str,
    preset: Preset,
    artifacts: dict[str, Path],
    rigging: RiggingResult,
    lod_count: int,
) -> Path:
    """Write the supported-editor contract for the staged asset.

    Forge deliberately does not write TPAC packages. This manifest makes every
    remaining TaleWorlds Resource Browser decision explicit and machine-readable.
    """

    geometry = artifacts.get("bannerlord_skinned_fbx")
    geometry = geometry or artifacts.get("bannerlord_provisional_skinned_fbx")
    geometry = geometry or artifacts.get("bannerlord_fbx")
    skinned = preset.rig_mode != "rigid"
    material_manifest_payload: dict[str, object] = {}
    material_manifest_path = artifacts.get("material_manifest")
    if material_manifest_path and material_manifest_path.is_file():
        material_manifest_payload = json.loads(material_manifest_path.read_text(encoding="utf-8"))
    material_mapping = material_manifest_payload.get("bannerlord_mapping", {})
    if not isinstance(material_mapping, dict):
        material_mapping = {}
    payload = {
        "schema": 1,
        "target": "Mount & Blade II: Bannerlord",
        "asset_id": asset_name,
        "equipment_slot": preset.key,
        "status": "modding_kit_import_required",
        "truth": {
            "tpac_compiled": False,
            "animation_tested": False,
            "in_game_tested": False,
            "automatic_rig_is_provisional": bool(rigging.status == "provisional_auto_weights"),
        },
        "geometry": {
            "preferred_fbx": str(geometry) if geometry else None,
            "review_glb": str(artifacts.get("prepared_glb", "")),
            "mesh_name": asset_name,
            "lod_names": [f"{asset_name}.lod{index}" for index in range(1, lod_count + 1)],
            "one_material_per_submesh": True,
            "resource_browser_import": {
                "recompute_normals": False,
                "recompute_tangents": True,
                "remove_redundant_vertices": True,
            },
        },
        "material": {
            "shader": "pbr_metallic",
            "compiler_manifest": str(artifacts.get("material_manifest", "")),
            "source_inspection": material_manifest_payload.get("source_material", {}),
            "generated_textures": {
                name.removeprefix("material_"): str(path)
                for name, path in artifacts.items()
                if name.startswith("material_") and name != "material_manifest"
            },
            "vertex_layout": {
                "bump_map": "material_normal" in artifacts,
                "skinning": skinned,
                "skinning_precise": False,
            },
            "recommended_alpha_mode": material_mapping.get("recommended_alpha_mode", "OPAQUE"),
            "texture_suffixes": {
                "albedo": "_d",
                "normal": "_n",
                "packed_specular": "_s",
                "height": "_h",
            },
            "packed_specular_channels": {
                "red": "metallic",
                "green": "glossiness (1 - roughness)",
                "blue": "ambient occlusion",
                "alpha": "translucency when the shader uses it",
            },
        },
        "skeleton": {
            "documented_max_bones": 64,
            "bone_name_suffix": "_<zero-based index>",
            "hierarchy_must_match": True,
            "ignored_import_skeleton_suffix": "_notused",
            "rigging_status": rigging.status,
            "rigging_method": rigging.method,
            "confidence": rigging.confidence,
        },
        "cloth": (
            {
                "required_review": True,
                "vertex_alpha_controls_max_distance": True,
                "zero_alpha_is_skinned_anchor": True,
                "separate_simulation_mesh_recommended_for_layered_or_dense_geometry": True,
                "collision_capsules_and_animation_preview_required": True,
            }
            if preset.rig_mode == "cloth"
            else None
        ),
        "module_handoff": {
            "copy_source_to": "<YourModule>/AssetSources",
            "editable_assets": "<YourModule>/Assets",
            "gameplay_xml": "<YourModule>/ModuleData",
            "publish_output": "<YourModule>/AssetPackages",
            "required_action": "Import with the matching Bannerlord Modding Kit Resource Browser, configure material/body/item XML, publish, then test in game.",
        },
    }
    path = output_dir / "bannerlord_import_manifest.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path
