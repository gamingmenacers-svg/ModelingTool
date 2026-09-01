"""Developer-only Blender script that generates an original two-bone test rig."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import bpy


def main() -> None:
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    opts = parser.parse_args(args)
    output = Path(opts.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    armature_data = bpy.data.armatures.new("ForgeTestRig")
    armature = bpy.data.objects.new("ForgeTestRig", armature_data)
    bpy.context.collection.objects.link(armature)
    bpy.context.view_layer.objects.active = armature
    armature.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    root = armature_data.edit_bones.new("root_0")
    root.head = (0.0, 0.0, 0.0)
    root.tail = (0.0, 0.0, 1.0)
    tip = armature_data.edit_bones.new("tip_1")
    tip.head = root.tail
    tip.tail = (0.0, 0.0, 2.0)
    tip.parent = root
    tip.use_connect = True
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.export_scene.fbx(
        filepath=str(output),
        use_selection=True,
        add_leaf_bones=False,
        bake_anim=False,
        axis_forward="-Z",
        axis_up="Y",
    )


if __name__ == "__main__":
    main()
