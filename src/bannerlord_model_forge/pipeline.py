from __future__ import annotations

import hashlib
import json
import re
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Callable

from .blender_backend import convert_with_blender, detect_blender, export_skinned_fbx
from .config import PRESETS, default_output_root
from .game_install import inspect_game_install
from .mesh_io import export_lod_scene, export_mesh, load_mesh, mesh_stats
from .models import PipelineResult
from .optimizer import clean_mesh, make_lods, quality_metrics, simplify_mesh
from .preview import render_preview
from .report import write_reports
from .rigging.base import RiggingRequest
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

    rig_request = RiggingRequest(
        prepared,
        job_dir / "rigging",
        reference_manifest=reference_manifest,
        rigid_bone=weapon_bone,
    )
    rigging = (
        WeaponRiggingBackend().rig(rig_request)
        if preset.key == "weapon"
        else ReferenceWeightTransferBackend().rig(rig_request)
    )
    if rigging.weights_path:
        artifacts["skin_weights"] = rigging.weights_path
    if rigging.metadata_path:
        artifacts["rigging_metadata"] = rigging.metadata_path
    blender_status = detect_blender()
    if preset.key == "weapon" and blender_status.found and enable_blender_export:
        weapon_fbx = geometry_dir / f"{asset_name}.fbx"
        if rigging.status == "rigid_asset_no_skinning":
            convert_with_blender(glb_path, weapon_fbx)
            artifacts["bannerlord_fbx"] = weapon_fbx
        elif rigging.weights_path and weapon_skeleton and weapon_skeleton.is_file():
            export_skinned_fbx(glb_path, weapon_skeleton, rigging.weights_path, weapon_fbx)
            artifacts["bannerlord_skinned_fbx"] = weapon_fbx
        elif rigging.status == "rigid_weights_generated":
            rigging.warnings.append("A one-bone weight map was generated, but no valid weapon skeleton FBX was supplied, so a skinned FBX was not exported.")
    elif rigging.weights_path and reference_manifest and blender_status.found and enable_blender_export:
        reference_data = json.loads(reference_manifest.read_text(encoding="utf-8"))
        configured_skeleton = reference_data.get("skeleton_fbx")
        if configured_skeleton:
            skeleton_path = Path(configured_skeleton).expanduser()
            if not skeleton_path.is_absolute():
                skeleton_path = (reference_manifest.parent / skeleton_path).resolve()
            if skeleton_path.is_file():
                skinned_fbx = geometry_dir / f"{asset_name}_skinned.fbx"
                export_skinned_fbx(glb_path, skeleton_path, rigging.weights_path, skinned_fbx)
                artifacts["bannerlord_skinned_fbx"] = skinned_fbx
            else:
                rigging.warnings.append("The reference manifest's skeleton_fbx path does not exist; no skinned FBX was exported.")
        else:
            rigging.warnings.append("Weights were transferred, but the reference manifest has no skeleton_fbx path; no skinned FBX was exported.")
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
    result = PipelineResult(
        source=source,
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
        result, inspect_game_install(), blender_status, _sha256(source)
    )
    artifacts["report_markdown"] = report_md
    artifacts["report_json"] = report_json
    say(f"Finished. Review {report_md.name} and the before/after previews.")
    return result
