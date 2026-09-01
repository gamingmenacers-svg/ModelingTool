"""Runs inside Blender, not the application Python environment."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import bpy


def arguments() -> argparse.Namespace:
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--skeleton")
    parser.add_argument("--weights")
    return parser.parse_args(args)


def main() -> None:
    opts = arguments()
    source = Path(opts.input)
    output = Path(opts.output)
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    suffix = source.suffix.lower()
    if suffix == ".fbx":
        bpy.ops.import_scene.fbx(filepath=str(source), use_anim=False)
    elif suffix in {".glb", ".gltf"}:
        bpy.ops.import_scene.gltf(filepath=str(source))
    elif suffix == ".obj":
        bpy.ops.wm.obj_import(filepath=str(source))
    else:
        raise ValueError(f"Unsupported Blender bridge input: {suffix}")
    imported_meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if opts.skeleton or opts.weights:
        if not (opts.skeleton and opts.weights):
            raise ValueError("Skinned export requires both --skeleton and --weights.")
        if len(imported_meshes) != 1:
            raise ValueError(f"Skinned export expects one prepared mesh, found {len(imported_meshes)}.")
        skeleton_path = Path(opts.skeleton)
        bpy.ops.import_scene.fbx(filepath=str(skeleton_path), use_anim=False)
        armatures = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]
        if not armatures:
            raise ValueError("No armature was found in the supplied skeleton FBX.")
        mesh_object = imported_meshes[0]
        armature = armatures[0]
        weight_data = json.loads(Path(opts.weights).read_text(encoding="utf-8"))
        rows = weight_data.get("weights", [])
        if len(rows) != len(mesh_object.data.vertices):
            raise ValueError(
                f"Weight row count {len(rows)} does not match imported vertex count {len(mesh_object.data.vertices)}."
            )
        available = {bone.name for bone in armature.data.bones}
        requested = set(weight_data.get("bones", []))
        missing = sorted(requested - available)
        if missing:
            raise ValueError(f"Skeleton is missing requested bones: {', '.join(missing[:12])}")
        groups = {name: mesh_object.vertex_groups.new(name=name) for name in sorted(requested)}
        for vertex_index, row in enumerate(rows):
            for bone_name, weight in row.items():
                groups[bone_name].add([vertex_index], float(weight), "REPLACE")
        modifier = mesh_object.modifiers.new(name="Bannerlord Armature", type="ARMATURE")
        modifier.object = armature
        mesh_object.parent = armature
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.suffix.lower() == ".glb":
        bpy.ops.export_scene.gltf(filepath=str(output), export_format="GLB", export_animations=False)
    elif output.suffix.lower() == ".fbx":
        if opts.skeleton and opts.weights:
            bpy.ops.object.select_all(action="DESELECT")
            for obj in imported_meshes + [armatures[0]]:
                obj.select_set(True)
        bpy.ops.export_scene.fbx(
            filepath=str(output),
            use_selection=bool(opts.skeleton and opts.weights),
            add_leaf_bones=False,
            bake_anim=False,
            axis_forward="-Z",
            axis_up="Y",
        )
    else:
        raise ValueError(f"Unsupported Blender bridge output: {output.suffix}")


if __name__ == "__main__":
    main()
