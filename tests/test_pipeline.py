import hashlib
import json
from pathlib import Path

from bannerlord_model_forge.pipeline import run_pipeline
from bannerlord_model_forge.sample import create_sample


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_end_to_end_is_non_destructive_and_generates_lods(tmp_path: Path) -> None:
    source = create_sample(tmp_path / "source.glb")
    source_hash = digest(source)

    result = run_pipeline(
        source,
        "body",
        triangle_target=1800,
        output_root=tmp_path / "output",
        enable_skeleton_preview=False,
    )

    assert digest(source) == source_hash
    assert result.before.triangles > result.after.triangles
    assert result.after.triangles <= 1800
    lod_counts = [item.triangles for item in result.lod_stats]
    assert lod_counts
    assert all(a > b for a, b in zip([result.after.triangles] + lod_counts, lod_counts))
    assert (result.output_dir / "preview_before.png").is_file()
    assert (result.output_dir / "preview_after.png").is_file()
    assert (result.output_dir / "validation_report.md").is_file()
    report = json.loads((result.output_dir / "validation_report.json").read_text(encoding="utf-8"))
    assert report["source"]["modified"] is False
    assert report["source"]["sha256"] == source_hash
    assert any(path.name.endswith(".lod1.obj") for path in result.artifacts.values())


def test_weapon_pipeline_emits_rigid_setup(tmp_path: Path) -> None:
    source = create_sample(tmp_path / "weapon.glb")
    result = run_pipeline(
        source,
        "weapon",
        triangle_target=1200,
        output_root=tmp_path / "output",
        enable_blender_export=False,
        enable_skeleton_preview=False,
    )
    assert result.rigging.status == "rigid_asset_no_skinning"
    assert result.artifacts["rigging_metadata"].name == "weapon_setup.json"
