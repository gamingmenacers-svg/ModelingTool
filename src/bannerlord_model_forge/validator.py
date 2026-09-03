from __future__ import annotations

import re

import numpy as np

from .config import Preset
from .models import MeshStats, QualityMetrics, ValidationItem


def _item(code: str, level: str, title: str, detail: str) -> ValidationItem:
    return ValidationItem(code, level, title, detail)


def validate_mesh(
    stats: MeshStats,
    preset: Preset,
    quality: QualityMetrics,
    lod_triangles: list[int],
) -> list[ValidationItem]:
    items: list[ValidationItem] = []
    if stats.triangles <= preset.triangle_target:
        items.append(_item("triangle_target", "pass", "Triangle target", f"{stats.triangles:,} triangles is within the {preset.triangle_target:,} policy target."))
    else:
        items.append(_item("triangle_target", "warning", "Triangle target", f"{stats.triangles:,} triangles exceeds the configurable {preset.triangle_target:,} policy target."))
    if stats.has_uv:
        items.append(_item("uv", "pass", "UV coordinates", "A per-vertex UV channel was detected."))
    else:
        items.append(_item("uv", "warning", "UV coordinates", "No per-vertex UV channel was detected; textured materials may not map correctly."))
    if stats.has_vertex_normals and stats.winding_consistent:
        items.append(_item("normals", "pass", "Normals and winding", "Vertex normals exist and face winding is consistent."))
    else:
        items.append(_item("normals", "warning", "Normals and winding", "Normals or face winding need review in the Bannerlord Resource Browser."))
    items.append(_item("tangents", "info", "Tangents", "Tangents are not preserved by the native MVP exporter; enable Recompute Tangents during Bannerlord import."))
    if stats.material_count <= 1:
        items.append(_item("materials", "pass", "Materials", "One material/submesh group was detected."))
    else:
        items.append(_item("materials", "info", "Materials", f"{stats.material_count} materials were detected. Bannerlord will split polygons into submeshes because each mesh uses one material."))
    items.append(
        _item(
            "pbr_material",
            "warning",
            "Bannerlord PBR material",
            "Create a pbr_metallic material in the Resource Browser. Pack metallic into specular R, glossiness (1 - roughness) into G, and ambient occlusion into B.",
        )
    )
    if preset.rig_mode != "rigid":
        items.append(
            _item(
                "skinning_material_flag",
                "warning",
                "Material skinning flag",
                "Enable Bump Map and Skinning in the material vertex layout. Use Skinning Precise only when important small polygons justify its extra cost.",
            )
        )
    items.append(
        _item(
            "texture_naming",
            "info",
            "Texture compilation hints",
            "Use the documented _d, _n, _s, and _h suffixes so the editor can infer albedo, normal, packed specular, and height-map compilation settings.",
        )
    )
    items.append(
        _item(
            "transforms",
            "info",
            "Scene transforms",
            f"Imported scene transforms were baked into the isolated derived mesh ({stats.transform_count} additional transform nodes reported); the source file was not changed.",
        )
    )
    height = float(np.max(stats.dimensions))
    low, high = preset.expected_height_m
    if low <= height <= high:
        items.append(_item("scale", "pass", "Approximate scale", f"Largest dimension is {height:.3f}; it is plausible for the {preset.label.lower()} preset if units are metres."))
    else:
        items.append(_item("scale", "warning", "Scale needs confirmation", f"Largest dimension is {height:.3f}. Expected roughly {low:.2f}–{high:.2f} metres for this preset; confirm units and orientation."))
    if preset.key == "body" and stats.dimensions[2] > 1e-8:
        horizontal_over_vertical = float(stats.dimensions[0] / stats.dimensions[2])
        if horizontal_over_vertical < 0.48:
            items.append(
                _item(
                    "bind_pose_span",
                    "warning",
                    "Rest-pose arm span",
                    "This body asset is narrow relative to its height. If it contains sleeves or arms authored down in an A/relaxed pose, deform it to the exact Bannerlord rest pose before transferring weights; centring alone is not a valid bind.",
                )
            )
    if preset.key == "weapon":
        diagonal = max(float(np.linalg.norm(stats.dimensions)), 1e-9)
        offset = float(np.linalg.norm(stats.bounds_center))
        if offset <= diagonal * 0.05:
            items.append(_item("weapon_origin", "pass", "Weapon origin", "The bounds centre is close to world origin, matching the documented crafting-piece starting convention."))
        else:
            items.append(_item("weapon_origin", "warning", "Weapon origin", f"Bounds centre is {offset:.4f} model units from world origin. Review pivot/grip placement; crafting pieces should be centred at origin."))
        items.append(_item("weapon_collision", "warning", "Weapon collision/body", "Visual geometry does not define safe combat collision by itself. Select or author the correct body/physics material in your module workflow."))
    elif preset.key == "shield":
        items.append(_item("shield_origin", "warning", "Shield grip/origin", "Confirm the shield grip, hand attachment, holster frame, and blocking orientation against the target item setup."))
        items.append(_item("shield_collision", "warning", "Shield collision/body", "The visual mesh is not a validated shield collision body; author and test the correct physics shape and material."))
    if preset.rig_mode == "cloth":
        items.append(_item("cloth", "warning", "Cloth setup required", "Weight transfer handles the skinned base only. Cloth vertex alpha, simulation mesh, collision capsules, and material settings still require Modding Kit tests."))
    items.append(_item("piece_guidance", "info", f"{preset.label} pose focus", preset.guidance))
    if lod_triangles and all(a > b for a, b in zip([stats.triangles] + lod_triangles, lod_triangles)):
        items.append(_item("lods", "pass", "LOD sequence", "LOD triangle counts decrease and names use Bannerlord's .lodN convention."))
    else:
        items.append(_item("lods", "warning", "LOD sequence", "No strictly decreasing LOD sequence was produced."))
    level = "pass" if quality.visible_loss == "low" else "warning"
    items.append(_item("quality", level, "Estimated visible loss", f"Deterministic nearest-vertex estimate is {quality.visible_loss}; maximum sampled deviation is {quality.nearest_vertex_max_percent_diagonal:.3f}% of the original bounding-box diagonal."))
    items.append(_item("clipping", "info", "Clipping risk", "Static geometry checks cannot prove clearance during animation. Test crouch, mount, combat, and extreme body shapes in the Modding Kit."))
    export_detail = (
        "The staged GLB/OBJ files are review intermediates. Export FBX and finish body, item/crafting XML, and attack/holster tests in the Bannerlord Modding Kit."
        if preset.rig_mode == "rigid"
        else "The staged GLB/OBJ files are review intermediates. A skinned FBX and Bannerlord Modding Kit import are still required for in-game use."
    )
    items.append(_item("export", "warning", "Bannerlord import and publish required", export_detail + " Forge does not mark an asset game-ready until Resource Browser import, module publish, and an in-game test pass."))
    return items


def validate_skeleton_manifest(bones: list[str]) -> list[ValidationItem]:
    items: list[ValidationItem] = []
    if not bones:
        return [_item("skeleton", "warning", "Skeleton missing", "No skeleton manifest was supplied.")]
    if len(bones) <= 64:
        items.append(_item("bone_count", "pass", "Bone count", f"{len(bones)} bones is within Bannerlord's documented 64-bone ceiling."))
    else:
        items.append(_item("bone_count", "error", "Bone count", f"{len(bones)} bones exceeds Bannerlord's documented 64-bone ceiling."))
    indices: list[int] = []
    invalid: list[str] = []
    for bone in bones:
        match = re.search(r"_(\d+)$", bone)
        if match:
            indices.append(int(match.group(1)))
        else:
            invalid.append(bone)
    if invalid:
        items.append(_item("bone_names", "warning", "Bone naming", f"{len(invalid)} bone names lack the documented _<index> suffix."))
    elif sorted(indices) == list(range(len(bones))):
        items.append(_item("bone_names", "pass", "Bone naming", "Bone suffix indices are unique and contiguous from zero."))
    else:
        items.append(_item("bone_names", "error", "Bone naming", "Bone suffix indices must be unique, contiguous, and lower than the bone count."))
    return items


def validate_weight_rows(
    bones: list[str], weights: list[dict[str, float]], max_influences: int
) -> list[ValidationItem]:
    if not weights:
        return [_item("weights", "warning", "Skin weights", "No skin-weight rows were supplied.")]
    bone_set = set(bones)
    too_many = 0
    bad_sum = 0
    unknown: set[str] = set()
    for row in weights:
        positive = {name: float(value) for name, value in row.items() if float(value) > 0}
        if len(positive) > max_influences:
            too_many += 1
        if abs(sum(positive.values()) - 1.0) > 1e-5:
            bad_sum += 1
        unknown.update(set(positive) - bone_set)
    items: list[ValidationItem] = []
    if too_many or bad_sum or unknown:
        items.append(
            _item(
                "weights",
                "error",
                "Skin weights",
                f"Invalid rows: {too_many} exceed {max_influences} influences, {bad_sum} are not normalized, and {len(unknown)} unknown bone names are referenced.",
            )
        )
    else:
        items.append(
            _item(
                "weights",
                "pass",
                "Skin weights",
                f"All {len(weights):,} rows are normalized, use known bones, and have at most {max_influences} influences.",
            )
        )
    items.append(
        _item(
            "bind_transforms",
            "warning",
            "Bind transforms",
            "Bone names and weights are structurally valid, but bind-pose transforms require Blender export and deformation tests against the exact target skeleton.",
        )
    )
    return items
