"""PyInstaller entry point with package-safe imports and a packaged smoke test."""

import json
import sys
from pathlib import Path

from bannerlord_model_forge.qt_app import main


def packaged_self_test(output_root: Path) -> int:
    from bannerlord_model_forge.pipeline import run_pipeline
    from bannerlord_model_forge.sample import create_sample

    output_root.mkdir(parents=True, exist_ok=True)
    marker = output_root / "self-test-result.json"
    try:
        source = create_sample(output_root / "self-test-source.glb")
        result = run_pipeline(
            source,
            "body",
            triangle_target=1800,
            output_root=output_root / "jobs",
            enable_blender_export=False,
        )
        material_manifest = result.artifacts.get("material_manifest")
        packed_specular = result.artifacts.get("material_packed_specular")
        if not material_manifest or not material_manifest.is_file():
            raise RuntimeError("Packaged material compiler did not create its manifest.")
        if not packed_specular or not packed_specular.is_file():
            raise RuntimeError("Packaged material compiler did not create a packed _s texture.")
        payload = {
            "status": "passed",
            "before_triangles": result.before.triangles,
            "after_triangles": result.after.triangles,
            "lod_triangles": [stats.triangles for stats in result.lod_stats],
            "output_dir": str(result.output_dir),
            "material_manifest": str(material_manifest),
            "packed_specular": str(packed_specular),
        }
        marker.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return 0
    except Exception as exc:
        marker.write_text(
            json.dumps({"status": "failed", "error": str(exc)}, indent=2),
            encoding="utf-8",
        )
        return 1


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--self-test":
        raise SystemExit(packaged_self_test(Path(sys.argv[2]).resolve()))
    main()
