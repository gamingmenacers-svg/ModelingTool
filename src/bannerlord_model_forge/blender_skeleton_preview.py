"""Render a local mesh and skeleton overlay inside Blender."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def arguments() -> argparse.Namespace:
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--skeleton", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--bannerlord-unit-scale", action="store_true")
    return parser.parse_args(args)


def make_material(name: str, color: tuple[float, float, float, float], metallic: float = 0.0):
    material = bpy.data.materials.new(name)
    material.diffuse_color = color
    material.use_nodes = True
    principled = material.node_tree.nodes.get("Principled BSDF")
    principled.inputs["Base Color"].default_value = color
    principled.inputs["Metallic"].default_value = metallic
    principled.inputs["Roughness"].default_value = 0.42
    return material


def look_at(camera, target: Vector) -> None:
    camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()


def main() -> None:
    opts = arguments()
    source = Path(opts.input)
    output = Path(opts.output)
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    bpy.ops.import_scene.gltf(filepath=str(source))
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if not meshes:
        raise ValueError("No mesh was imported for the skeleton preview.")
    mesh_material = make_material("ForgeMesh", (0.035, 0.30, 0.72, 1.0), metallic=0.45)
    for obj in meshes:
        obj.data.materials.clear()
        obj.data.materials.append(mesh_material)

    bpy.ops.import_scene.fbx(filepath=str(Path(opts.skeleton)), use_anim=False)
    armatures = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]
    if not armatures:
        raise ValueError("No armature was found in the skeleton FBX.")
    if opts.bannerlord_unit_scale:
        for armature in armatures:
            armature.scale = tuple(value * 100.0 for value in armature.scale)
        bpy.context.view_layer.update()
    skeleton_material = make_material("ForgeSkeleton", (1.0, 0.09, 0.035, 1.0))
    curve_data = bpy.data.curves.new("ForgeSkeletonLines", type="CURVE")
    curve_data.dimensions = "3D"
    curve_data.resolution_u = 1
    bone_points: list[Vector] = []
    bone_records: list[dict[str, object]] = []
    for armature in armatures:
        for bone in armature.data.bones:
            head = armature.matrix_world @ bone.head_local
            tail = armature.matrix_world @ bone.tail_local
            bone_points.extend((head, tail))
            bone_records.append(
                {
                    "name": bone.name,
                    "head": list(head),
                    "tail": list(tail),
                    "parent": bone.parent.name if bone.parent else None,
                }
            )
            spline = curve_data.splines.new("POLY")
            spline.points.add(1)
            spline.points[0].co = (*head, 1.0)
            spline.points[1].co = (*tail, 1.0)
    if not bone_points:
        raise ValueError("The skeleton armature contains no bones.")

    mesh_points = [obj.matrix_world @ Vector(corner) for obj in meshes for corner in obj.bound_box]
    all_points = mesh_points + bone_points
    minimum = Vector(tuple(min(point[index] for point in all_points) for index in range(3)))
    maximum = Vector(tuple(max(point[index] for point in all_points) for index in range(3)))
    center = (minimum + maximum) * 0.5
    extents = maximum - minimum
    diagonal = max(extents.length, 0.01)
    curve_data.bevel_depth = diagonal * 0.0045
    curve_data.bevel_resolution = 2
    skeleton_lines = bpy.data.objects.new("BannerlordSkeletonOverlay", curve_data)
    bpy.context.collection.objects.link(skeleton_lines)
    skeleton_lines.data.materials.append(skeleton_material)

    camera_data = bpy.data.cameras.new("ForgeCamera")
    camera_data.type = "ORTHO"
    camera_data.ortho_scale = max(extents.x, extents.z, extents.y) * 1.28
    camera = bpy.data.objects.new("ForgeCamera", camera_data)
    bpy.context.collection.objects.link(camera)
    camera.location = center + Vector((diagonal * 1.25, -diagonal * 1.75, diagonal * 0.85))
    look_at(camera, center)
    bpy.context.scene.camera = camera

    for location, energy, size in [
        ((4, -5, 7), 1050, 5.0),
        ((-4, -2, 3), 700, 4.0),
        ((2, 4, 1), 500, 3.0),
    ]:
        light_data = bpy.data.lights.new(type="AREA", name="ForgeLight")
        light_data.energy = energy
        light_data.shape = "DISK"
        light_data.size = size
        light = bpy.data.objects.new("ForgeLight", light_data)
        bpy.context.collection.objects.link(light)
        light.location = center + Vector(location) * (diagonal / 6.0)
        look_at(light, center)

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 720
    scene.render.resolution_y = 720
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(output)
    scene.render.film_transparent = False
    scene.world.color = (0.008, 0.012, 0.022)
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.render.render(write_still=True)
    output.with_suffix(".json").write_text(
        json.dumps(
            {
                "schema": 1,
                "source_model": str(source),
                "skeleton_source": str(Path(opts.skeleton)),
                "bones": bone_records,
                "note": "Local visual alignment data; the skeleton source file was read only and was not copied.",
                "bannerlord_unit_scale_applied": bool(opts.bannerlord_unit_scale),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
