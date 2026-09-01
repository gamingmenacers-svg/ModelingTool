from __future__ import annotations

import copy
import logging
from pathlib import Path
from typing import Iterable

import numpy as np
import trimesh

from .models import MeshStats


NATIVE_FORMATS = {".obj", ".glb", ".gltf", ".ply", ".stl"}
BLENDER_FORMATS = {".fbx"}
SUPPORTED_FORMATS = NATIVE_FORMATS | BLENDER_FORMATS


class MeshImportError(RuntimeError):
    pass


def _material_names(mesh: trimesh.Trimesh) -> list[str]:
    material = getattr(mesh.visual, "material", None)
    name = getattr(material, "name", None)
    return [str(name)] if name else []


def _texture_references(mesh: trimesh.Trimesh) -> list[str]:
    refs: list[str] = []
    material = getattr(mesh.visual, "material", None)
    if material is None:
        return refs
    for field in ("image", "baseColorTexture", "normalTexture", "emissiveTexture"):
        value = getattr(material, field, None)
        if isinstance(value, (str, Path)):
            refs.append(str(value))
        elif value is not None and hasattr(value, "filename") and value.filename:
            refs.append(str(value.filename))
    return sorted(set(refs))


def load_mesh(path: Path) -> tuple[trimesh.Trimesh, dict[str, int]]:
    path = path.expanduser().resolve()
    if not path.is_file():
        raise MeshImportError(f"Model does not exist: {path}")
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_FORMATS:
        raise MeshImportError(
            f"Unsupported format {suffix or '(none)'}. Use OBJ, GLB/GLTF, PLY, STL, or FBX."
        )
    if suffix in BLENDER_FORMATS:
        raise MeshImportError(
            "FBX needs the optional Blender backend. Install Blender, then convert the FBX "
            "to GLB in the dependency step; the source FBX will remain untouched."
        )
    try:
        loaded = trimesh.load(path, force="scene", process=False)
    except Exception as exc:  # format loaders expose several exception types
        raise MeshImportError(f"Could not import {path.name}: {exc}") from exc
    if isinstance(loaded, trimesh.Trimesh):
        scene = trimesh.Scene(loaded)
    elif isinstance(loaded, trimesh.Scene):
        scene = loaded
    else:
        raise MeshImportError(f"No triangle mesh was found in {path.name}.")

    dumped = scene.dump()
    meshes = [m for m in dumped if isinstance(m, trimesh.Trimesh) and len(m.faces)]
    if not meshes:
        raise MeshImportError(f"No triangle faces were found in {path.name}.")
    combined = trimesh.util.concatenate(meshes)
    combined.metadata["source_material_names"] = sorted(
        set(name for mesh in meshes for name in _material_names(mesh))
    )
    combined.metadata["texture_references"] = sorted(
        set(ref for mesh in meshes for ref in _texture_references(mesh))
    )
    context = {
        "source_geometry_count": len(scene.geometry),
        "transform_count": max(0, len(scene.graph.nodes_geometry) - len(scene.geometry)),
    }
    return combined, context


def mesh_stats(mesh: trimesh.Trimesh, context: dict[str, int] | None = None) -> MeshStats:
    context = context or {}
    uv = getattr(mesh.visual, "uv", None)
    normal_logger = logging.getLogger("trimesh.util")
    previous_level = normal_logger.level
    normal_logger.setLevel(logging.ERROR)
    try:
        normals = np.asarray(mesh.vertex_normals) if len(mesh.vertices) else np.empty((0, 3))
    finally:
        normal_logger.setLevel(previous_level)
    source_materials = mesh.metadata.get("source_material_names", [])
    texture_refs = mesh.metadata.get("texture_references", [])
    components = _component_count(np.asarray(mesh.faces, dtype=int), len(mesh.vertices))
    bounds = np.asarray(mesh.bounds, dtype=float)
    return MeshStats(
        vertices=int(len(mesh.vertices)),
        triangles=int(len(mesh.faces)),
        components=int(components),
        material_count=max(1, len(source_materials)),
        bounds_min=np.round(bounds[0], 6).tolist(),
        bounds_max=np.round(bounds[1], 6).tolist(),
        dimensions=np.round(mesh.extents, 6).tolist(),
        bounds_center=np.round((bounds[0] + bounds[1]) / 2.0, 6).tolist(),
        watertight=bool(mesh.is_watertight),
        winding_consistent=bool(mesh.is_winding_consistent),
        has_vertex_normals=bool(len(normals) == len(mesh.vertices) and len(normals)),
        has_uv=bool(uv is not None and len(uv) == len(mesh.vertices)),
        has_tangents=False,
        texture_references=list(texture_refs),
        source_geometry_count=int(context.get("source_geometry_count", 1)),
        transform_count=int(context.get("transform_count", 0)),
    )


def _component_count(faces: np.ndarray, vertex_count: int) -> int:
    """Count face-connected components without an optional graph dependency."""
    if not len(faces):
        return 0
    parent = np.arange(vertex_count, dtype=int)

    def find(value: int) -> int:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = int(parent[value])
        return value

    def union(a: int, b: int) -> None:
        root_a, root_b = find(a), find(b)
        if root_a != root_b:
            parent[root_b] = root_a

    for a, b, c in faces:
        union(int(a), int(b))
        union(int(b), int(c))
    used = np.unique(faces)
    return len({find(int(vertex)) for vertex in used})


def clone_mesh(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    return copy.deepcopy(mesh)


def export_mesh(mesh: trimesh.Trimesh, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exported = mesh.export(file_type=path.suffix.lstrip("."))
    if isinstance(exported, str):
        path.write_text(exported, encoding="utf-8")
    else:
        path.write_bytes(bytes(exported))


def export_lod_scene(named_meshes: Iterable[tuple[str, trimesh.Trimesh]], path: Path) -> None:
    scene = trimesh.Scene()
    for name, mesh in named_meshes:
        scene.add_geometry(mesh, geom_name=name, node_name=name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(scene.export(file_type="glb"))
