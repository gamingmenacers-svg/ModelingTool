"""Extract rest-pose bone geometry from a local FBX without modifying it."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import bpy


def arguments() -> argparse.Namespace:
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--skeleton", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--scale", type=float, default=1.0)
    return parser.parse_args(args)


def main() -> None:
    opts = arguments()
    source = Path(opts.skeleton).resolve()
    output = Path(opts.output).resolve()
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    bpy.ops.import_scene.fbx(filepath=str(source), use_anim=False)
    armatures = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]
    if not armatures:
        raise ValueError("No armature was found in the skeleton FBX.")

    records: list[dict[str, object]] = []
    for armature in armatures:
        matrix = armature.matrix_world
        for bone in armature.data.bones:
            head = (matrix @ bone.head_local) * opts.scale
            tail = (matrix @ bone.tail_local) * opts.scale
            records.append(
                {
                    "name": bone.name,
                    "head": [float(value) for value in head],
                    "tail": [float(value) for value in tail],
                    "parent": bone.parent.name if bone.parent else None,
                    "connected": bool(bone.use_connect),
                }
            )
    if not records:
        raise ValueError("The skeleton armature contains no bones.")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "schema": 1,
                "skeleton_source": str(source),
                "bone_count": len(records),
                "bones": records,
                "scale_applied": float(opts.scale),
                "note": "Rest-pose data extracted read-only from the locally installed FBX.",
            },
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
