from __future__ import annotations

import hashlib
import json
import re
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Callable

from .blender_backend import (
    convert_with_blender,
    detect_blender,
    export_skinned_fbx,
    render_skeleton_overlay,
)
from .config import BONE_REGION_PATTERNS, PRESETS, default_output_root
from .game_install import inspect_game_install
from .mesh_io import export_lod_scene, export_mesh, load_mesh, mesh_stats
from .models import PipelineResult, ValidationItem
from .optimizer import clean_mesh, make_lods, quality_metrics, simplify_mesh
from .preview import render_preview
from .report import write_reports
from .rigging.base import ManualRiggingBackend, RiggingRequest
from .rigging.proximity import SkeletonProximityRiggingBackend
from .rigging.reference_transfer import ReferenceWeightTransferBackend
from .rigging.weapon import WeaponRiggingBackend
from .validator import validate_mesh, validate_skeleton_manifest, validate_weight_rows


Progress = Callable[[str], None]


def _slug(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_-]+", "_", value).strip("_")
    return value[:64] or "model"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run_pipeline(
    source: Path,
    preset_key: str,
    triangle_target: int | None = None,
    output_root: Path | None = None,
    reference_manifest: Path | None = None,
    weapon_bone: str | None = None,
    weapon_skeleton: Path | None = None,
    enable_blender_export: bool = True,
    enable_skeleton_preview: bool = True,
    progress: Progress | None = None,
) -> PipelineResult:
    say = progress or (lambda _message: None)
    source = source.expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if preset_key not in PRESETS:
        raise ValueError(f"Unknown preset: {preset_key}")
    preset = PRESETS[preset_key]
    target = int(triangle_target or preset.triangle_target)
    if target < 4:
        raise ValueError("Triangle target must be at least 4.")
    root = (output_root or default_output_root()).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    job_dir = root / f"{_slug(source.stem)}-{preset.key}-{stamp}"
    job_dir.mkdir(parents=False, exist_ok=False)
    say(f"Created isolated output: {job_dir}")

    import_path = source
    if source.suffix.lower() == ".fbx":
        say("Converting FBX through Blender in the output workspace...")
        import_path = convert_with_blender(source, job_dir / "intermediate" / "source_converted.glb")
    say("Importing mesh without changing the source...")
    original, context = load_mesh(import_path)
    before = mesh_stats(original, context)
    say(f"Found {before.vertices:,} vertices and {before.triangles:,} triangles.")

    blender_status = detect_blender()
    material = getattr(original.visual, "material", None)
    has_texture = bool(
        getattr(original.visual, "uv", None) is not None
        and material is not None
        and (
            getattr(material, "baseColorTexture", None) is not None
            or getattr(material, "image", None) is not None
        )
    )
    if len(original.faces) > target and has_texture and blender_status.found:
        say("Reducing triangles through Blender so UVs and the material texture remain intact...")
        textured_input = job_dir / "intermediate" / "source_textured.glb"
        textured_output = job_dir / "intermediate" / "decimated_textured.glb"
        export_mesh(original, textured_input)
        convert_with_blender(textured_input, textured_output, target_faces=target)
        prepared, _prepared_context = load_mesh(textured_output)
    elif len(original.faces) > target and has_texture:
        say("Blender is unavailable, so triangle reduction was skipped rather than destroying the UV texture.")
        prepared = original
    else:
        cleaned = clean_mesh(original)
        prepared = simplify_mesh(cleaned, target)
    after = mesh_stats(prepared, context)
    say(f"Prepared base mesh: {after.triangles:,} triangles.")
    lods = make_lods(prepared, preset.lod_ratios)
    lod_stats = [mesh_stats(lod, context) for lod in lods]
    quality = quality_metrics(original, prepared)

    asset_name = _slug(source.stem).lower()
    geometry_dir = job_dir / "geometry"
    glb_path = geometry_dir / f"{asset_name}.glb"
    obj_path = geometry_dir / f"{asset_name}.obj"
    export_mesh(prepared, glb_path)
    export_mesh(prepared, obj_path)
    artifacts: dict[str, Path] = {"prepared_glb": glb_path, "prepared_obj": obj_path}
    named = [(asset_name, prepared)]
    for index, lod in enumerate(lods, start=1):
        lod_name = f"{asset_name}.lod{index}"
        lod_path = geometry_dir / f"{lod_name}.obj"
        export_mesh(lod, lod_path)
        artifacts[f"lod{index}_obj"] = lod_path
        named.append((lod_name, lod))
    lod_bundle = geometry_dir / f"{asset_name}_with_lods.glb"
    export_lod_scene(named, lod_bundle)
    artifacts["lod_bundle_glb"] = lod_bundle

    render_preview(original, job_dir / "preview_before.png", "Original (read-only)")
    render_preview(prepared, job_dir / "preview_after.png", "Prepared base mesh")
    artifacts["preview_before"] = job_dir / "preview_before.png"
    artifacts["preview_after"] = job_dir / "preview_after.png"

    game_info = inspect_game_install()
    reference_data: dict[str, object] = {}
    if reference_manifest and reference_manifest.is_file():
        reference_data = json.loads(reference_manifest.read_text(encoding="utf-8"))
    configured_skeleton: object = reference_data.get("skeleton_fbx")
    resolved_reference_skeleton: Path | None = None
    if configured_skeleton:
        resolved_reference_skeleton = Path(str(configured_skeleton)).expanduser()
        if not resolved_reference_skeleton.is_absolute():
            resolved_reference_skeleton = (reference_manifest.parent / resolved_reference_skeleton).resolve()

    preview_skeleton: Path | None = None
    preview_kind = "alignment_guide"
    preview_bannerlord_unit_scale = False
    if preset.rig_mode == "rigid":
        if weapon_skeleton and weapon_skeleton.is_file():
            preview_skeleton = weapon_skeleton
            preview_kind = "supplied_rigid_rig"
    elif resolved_reference_skeleton and resolved_reference_skeleton.is_file():
        preview_skeleton = resolved_reference_skeleton
        preview_kind = "weighted_reference_rig"
    elif game_info.human_skeleton_path:
        candidate = Path(game_info.human_skeleton_path)
        if candidate.is_file():
            preview_skeleton = candidate
            preview_bannerlord_unit_scale = True

    if enable_skeleton_preview and blender_status.found and preview_skeleton:
        say("Rendering the model with its skeleton alignment overlay...")
        try:
            overlay_png, overlay_json = render_skeleton_overlay(
                glb_path,
                preview_skeleton,
                job_dir / "skeleton_overlay.png",
                bannerlord_unit_scale=preview_bannerlord_unit_scale,
            )
            artifacts["skeleton_overlay"] = overlay_png
            artifacts["skeleton_viewport_data"] = overlay_json
        except Exception as exc:
            say(f"Skeleton visual preview was unavailable: {exc}")

    rig_request = RiggingRequest(
        prepared,
        job_dir / "rigging",
        reference_manifest=reference_manifest,
        rigid_bone=weapon_bone,
        asset_kind=preset.key,
    )
    if preset.rig_mode == "rigid":
        rigging = WeaponRiggingBackend().rig(rig_request)
    elif reference_manifest and reference_manifest.is_file():
        rigging = ReferenceWeightTransferBackend().rig(rig_request)
    elif "skeleton_viewport_data" in artifacts:
        patterns = BONE_REGION_PATTERNS.get(preset.skeleton_region, ())
        rigging = SkeletonProximityRiggingBackend(
            artifacts["skeleton_viewport_data"], patterns
        ).rig(rig_request)
    else:
        rigging = ManualRiggingBackend().rig(rig_request)
    if rigging.weights_path:
        artifacts["skin_weights"] = rigging.weights_path
    if rigging.metadata_path:
        artifacts["rigging_metadata"] = rigging.metadata_path

    if preset.rig_mode == "rigid" and blender_status.found and enable_blender_export:
        rigid_fbx = geometry_dir / f"{asset_name}.fbx"
        if rigging.status == "rigid_asset_no_skinning":
            convert_with_blender(glb_path, rigid_fbx)
            artifacts["bannerlord_fbx"] = rigid_fbx
        elif rigging.weights_path and weapon_skeleton and weapon_skeleton.is_file():
            export_skinned_fbx(glb_path, weapon_skeleton, rigging.weights_path, rigid_fbx)
            artifacts["bannerlord_skinned_fbx"] = rigid_fbx
        elif rigging.status == "rigid_weights_generated":
            rigging.warnings.append("A one-bone weight map was generated, but no valid weapon skeleton FBX was supplied, so a skinned FBX was not exported.")
    elif rigging.weights_path and reference_manifest and blender_status.found and enable_blender_export:
        if resolved_reference_skeleton:
            if resolved_reference_skeleton.is_file():
                skinned_fbx = geometry_dir / f"{asset_name}_skinned.fbx"
                export_skinned_fbx(glb_path, resolved_reference_skeleton, rigging.weights_path, skinned_fbx)
                artifacts["bannerlord_skinned_fbx"] = skinned_fbx
            else:
                rigging.warnings.append("The reference manifest's skeleton_fbx path does not exist; no skinned FBX was exported.")
        else:
            rigging.warnings.append("Weights were transferred, but the reference manifest has no skeleton_fbx path; no skinned FBX was exported.")
    if (
        rigging.status == "provisional_auto_weights"
        and rigging.weights_path
        and preview_skeleton
        and blender_status.found
        and enable_blender_export
    ):
        provisional_fbx = geometry_dir / f"{asset_name}_provisional_skinned.fbx"
        try:
            export_skinned_fbx(
                glb_path,
                preview_skeleton,
                rigging.weights_path,
                provisional_fbx,
                bannerlord_unit_scale=preview_bannerlord_unit_scale,
            )
            artifacts["bannerlord_provisional_skinned_fbx"] = provisional_fbx
        except Exception as exc:
            rigging.warnings.append(f"Provisional skinned FBX could not be exported: {exc}")
    validation = validate_mesh(
        after,
        replace(preset, triangle_target=target),
        quality,
        [stats.triangles for stats in lod_stats],
    )
    if rigging.weights_path and rigging.weights_path.is_file():
        weight_payload = json.loads(rigging.weights_path.read_text(encoding="utf-8"))
        bones = [str(name) for name in weight_payload.get("bones", [])]
        validation.extend(validate_skeleton_manifest(bones))
        validation.extend(
            validate_weight_rows(
                bones,
                weight_payload.get("weights", []),
                int(weight_payload.get("max_influences", 4)),
            )
        )
    if "skeleton_overlay" in artifacts:
        validation.append(
            ValidationItem(
                "skeleton_visual",
                "info",
                "Skeleton visual inspection",
                f"A {preview_kind.replace('_', ' ')} overlay was generated. It reveals scale/orientation/bone placement, but does not by itself prove deformation quality.",
            )
        )
    result = PipelineResult(
        source=source,
        preset_key=preset.key,
        output_dir=job_dir,
        before=before,
        after=after,
        lod_stats=lod_stats,
        quality=quality,
        validation=validation,
        rigging=rigging,
        artifacts=artifacts,
    )
    report_md, report_json = write_reports(
        result, game_info, blender_status, _sha256(source)
    )
    artifacts["report_markdown"] = report_md
    artifacts["report_json"] = report_json
    say(f"Finished. Review {report_md.name} and the before/after previews.")
    return result
