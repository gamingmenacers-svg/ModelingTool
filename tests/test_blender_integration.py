import json
import os
import subprocess
from pathlib import Path

import pytest

from bannerlord_model_forge.blender_backend import detect_blender
from bannerlord_model_forge.mesh_io import load_mesh
from bannerlord_model_forge.pipeline import run_pipeline
from bannerlord_model_forge.sample import create_sample


@pytest.mark.skipif(
    os.environ.get("BMF_RUN_BLENDER_TESTS") != "1",
    reason="set BMF_RUN_BLENDER_TESTS=1 to run the installed-Blender integration test",
)
def test_skinned_fbx_export_with_generated_legal_rig(tmp_path: Path) -> None:
    blender = detect_blender()
    if not blender.found or not blender.executable:
        pytest.skip("Blender is not installed")
    project_root = Path(__file__).resolve().parents[1]
    skeleton = tmp_path / "test_skeleton.fbx"
    completed = subprocess.run(
        [
            blender.executable,
            "--background",
            "--factory-startup",
            "--python",
            str(project_root / "scripts" / "blender_make_test_skeleton.py"),
            "--",
            "--output",
            str(skeleton),
        ],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    source = create_sample(tmp_path / "source.glb")
    mesh, _ = load_mesh(source)
    manifest = tmp_path / "reference.json"
    manifest.write_text(
        json.dumps(
            {
                "skeleton_fbx": str(skeleton),
                "bones": ["root_0", "tip_1"],
                "vertices": mesh.vertices.tolist(),
                "weights": [{"root_0": 1.0} for _ in mesh.vertices],
            }
        ),
        encoding="utf-8",
    )
    result = run_pipeline(
        source,
        "body",
        triangle_target=len(mesh.faces),
        output_root=tmp_path / "output",
        reference_manifest=manifest,
    )
    assert result.rigging.status == "weights_transferred"
    assert result.artifacts["bannerlord_skinned_fbx"].is_file()
    assert result.artifacts["skeleton_overlay"].is_file()
    assert result.artifacts["skeleton_viewport_data"].is_file()
