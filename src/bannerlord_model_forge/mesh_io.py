from __future__ import annotations

import copy
import logging
from collections import Counter
from dataclasses import dataclass, field
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


@dataclass
class MeshPart:
    """One selectable scene object with its material and node transform retained."""

    name: str
    mesh: trimesh.Trimesh
    # Non-destructive working transform. The imported mesh and its UV/material
    # stay untouched until the selected piece is handed to the rigging pipeline.
    transform: np.ndarray = field(default_factory=lambda: np.eye(4, dtype=float))

    def transformed_mesh(self) -> trimesh.Trimesh:
        result = self.mesh.copy()
        matrix = np.asarray(self.transform, dtype=float)
        if not np.allclose(matrix, np.eye(4), rtol=0.0, atol=1e-12):
            result.apply_transform(matrix)
        return result


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


def load_mesh_parts(path: Path) -> tuple[list[MeshPart], dict[str, int]]:
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

    parts: list[MeshPart] = []
    geometry_uses = Counter(str(scene.graph[node_name][1]) for node_name in scene.graph.nodes_geometry)
    for node_name in scene.graph.nodes_geometry:
        transform, geometry_name = scene.graph[node_name]
        source_mesh = scene.geometry.get(geometry_name)
        if not isinstance(source_mesh, trimesh.Trimesh) or not len(source_mesh.faces):
            continue
        # A GLB may instance one geometry from several nodes. Avoid copying the
        # very large embedded texture unless the actual geometry is reused.
        mesh = source_mesh.copy() if geometry_uses[str(geometry_name)] > 1 else source_mesh
        matrix = np.asarray(transform, dtype=float)
        if not np.allclose(matrix, np.eye(4), rtol=0.0, atol=1e-12):
            mesh.apply_transform(matrix)
        display_name = str(node_name or geometry_name or f"piece {len(parts) + 1:02d}")
        parts.append(MeshPart(display_name, mesh))
    if not parts:
        raise MeshImportError(f"No triangle faces were found in {path.name}.")
    context = {
        "source_geometry_count": len(scene.geometry),
        "transform_count": max(0, len(scene.graph.nodes_geometry) - len(scene.geometry)),
    }
    return parts, context


def combine_mesh_parts(parts: Iterable[MeshPart]) -> trimesh.Trimesh:
    part_list = list(parts)
    if not part_list:
        raise MeshImportError("No visible mesh pieces remain in the working scene.")
    meshes = [part.mesh for part in part_list]
    combined = trimesh.util.concatenate(meshes)
    combined.metadata["source_material_names"] = sorted(
        set(name for mesh in meshes for name in _material_names(mesh))
    )
    combined.metadata["texture_references"] = sorted(
        set(ref for mesh in meshes for ref in _texture_references(mesh))
    )
    combined.metadata["source_part_names"] = [part.name for part in part_list]
    combined.metadata["known_component_count"] = len(part_list)
    return combined


def load_mesh(path: Path) -> tuple[trimesh.Trimesh, dict[str, int]]:
    parts, context = load_mesh_parts(path)
    combined = combine_mesh_parts(parts)
    return combined, context


def mesh_stats(mesh: trimesh.Trimesh, context: dict[str, int] | None = None) -> MeshStats:
    context = context or {}
    uv = getattr(mesh.visual, "uv", None)
    # Trimesh falls back to a very slow Python sparse-normal path when SciPy is
    # intentionally absent from the lightweight desktop build. Dense imports
    # already carry renderable triangle normals, so don't block for minutes on
    # a reporting-only vertex-normal check.
    if len(mesh.vertices) > 75_000:
        has_vertex_normals = bool(len(mesh.faces))
    else:
        normal_logger = logging.getLogger("trimesh.util")
        previous_level = normal_logger.level
        normal_logger.setLevel(logging.ERROR)
        try:
            normals = np.asarray(mesh.vertex_normals) if len(mesh.vertices) else np.empty((0, 3))
        finally:
            normal_logger.setLevel(previous_level)
        has_vertex_normals = bool(len(normals) == len(mesh.vertices) and len(normals))
    source_materials = mesh.metadata.get("source_material_names", [])
    texture_refs = mesh.metadata.get("texture_references", [])
    known_components = mesh.metadata.get("known_component_count")
    components = (
        int(known_components)
        if isinstance(known_components, (int, np.integer)) and int(known_components) > 0
        else _component_count(np.asarray(mesh.faces, dtype=int), len(mesh.vertices))
    )
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
        has_vertex_normals=has_vertex_normals,
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
