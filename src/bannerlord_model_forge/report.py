from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .blender_backend import BlenderStatus
from .game_install import GameInstallInfo
from .models import PipelineResult


def write_reports(
    result: PipelineResult,
    game: GameInstallInfo,
    blender: BlenderStatus,
    source_sha256: str,
) -> tuple[Path, Path]:
    json_path = result.output_dir / "validation_report.json"
    markdown_path = result.output_dir / "validation_report.md"
    payload = {
        "schema": 1,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "source": {"path": str(result.source), "sha256": source_sha256, "modified": False},
        "game_install": game.to_dict(),
        "blender": blender.to_dict(),
        "before": result.before.to_dict(),
        "after": result.after.to_dict(),
        "lods": [stats.to_dict() for stats in result.lod_stats],
        "quality": result.quality.to_dict(),
        "rigging": result.rigging.to_dict(),
        "validation": [item.to_dict() for item in result.validation],
        "artifacts": {name: str(path) for name, path in result.artifacts.items()},
    }
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    verdict = "READY FOR MANUAL MODDING-KIT REVIEW"
    if any(item.level == "error" for item in result.validation):
        verdict = "BLOCKED BY VALIDATION ERRORS"
    elif result.rigging.status not in {"weights_transferred", "rigid_asset_no_skinning", "rigid_weights_generated"}:
        verdict = "MESH PREPARED; RIGGING/EDITOR REVIEW STILL REQUIRED"
    rows = "\n".join(
        f"- **{item.level.upper()} — {item.title}:** {item.detail}" for item in result.validation
    )
    rig_warnings = "\n".join(f"- {warning}" for warning in result.rigging.warnings)
    if result.rigging.method in {"bannerlord_rigid_item", "rigid_one_bone"}:
        next_steps = """1. Inspect `preview_before.png` and `preview_after.png` for silhouette changes.
2. Correct the pivot/origin and grip alignment; ordinary crafting pieces should be numerically centred at world origin.
3. Export FBX through the optional Blender backend or another trusted DCC workflow.
4. In your own module, configure the appropriate body/physics material and item or crafting XML, then test attacks, holstering, projectiles, and collision in the Modding Kit."""
    else:
        next_steps = """1. Inspect `preview_before.png` and `preview_after.png` for silhouette changes.
2. Supply a legally usable, close-fitting weighted reference template. The official human skeleton alone is not enough to guarantee good weights.
3. Produce a skinned FBX through the optional Blender backend, then place it in your own module's `AssetSources` folder.
4. In the Bannerlord Modding Kit Resource Browser, scan/import it, create matching materials, enable skinning, recompute tangents if needed, and test animations/clipping."""
    markdown = f"""# Bannerlord Model Forge validation report

**Verdict:** {verdict}

The source file was read only. Its SHA-256 fingerprint is `{source_sha256}`.

## Before and after

| Measure | Before | Prepared |
| --- | ---: | ---: |
| Vertices | {result.before.vertices:,} | {result.after.vertices:,} |
| Triangles | {result.before.triangles:,} | {result.after.triangles:,} |
| Components | {result.before.components} | {result.after.components} |
| Materials | {result.before.material_count} | {result.after.material_count} |

Estimated visible loss: **{result.quality.visible_loss}**. Sampled maximum geometric deviation is {result.quality.nearest_vertex_max_percent_diagonal:.3f}% of the original bounds diagonal.

## Validation

{rows}

## Rigging confidence

Status: **{result.rigging.status}**<br>
Method: `{result.rigging.method}`<br>
Confidence: **{result.rigging.confidence:.0%}**

{rig_warnings}

## What to do next

{next_steps}

Game detected: `{game.version or 'unknown version'}`; editor: `{game.editor_found}`. Blender detected: `{blender.found}`.
"""
    markdown_path.write_text(markdown, encoding="utf-8")
    return markdown_path, json_path
