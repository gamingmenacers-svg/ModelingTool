from __future__ import annotations

import copy
from pathlib import Path
from typing import Iterable

import trimesh

from .material_compiler import inspect_source_material
from .mesh_io import MeshPart


def export_material_preview(parts: Iterable[MeshPart], path: Path) -> Path:
    """Export a render-only GLB while preserving source UVs and shared materials.

    Some FBX exporters tag a fully opaque base-colour atlas as alpha blended.
    Transparent sorting then produces missing/black triangles in real-time
    renderers. We correct only that provably invalid alpha flag in this derived
    preview; the source file and in-memory working meshes remain untouched.
    """

    scene = trimesh.Scene()
    material_copies: dict[int, object] = {}
    for index, part in enumerate(parts):
        mesh = part.transformed_mesh()
        source_material = getattr(getattr(part.mesh, "visual", None), "material", None)
        if source_material is not None:
            material_key = id(source_material)
            if material_key not in material_copies:
                preview_material = copy.deepcopy(source_material)
                inspection = inspect_source_material(part.mesh)
                if not inspection.meaningful_alpha:
                    setattr(preview_material, "alphaMode", "OPAQUE")
                material_copies[material_key] = preview_material
            mesh.visual.material = material_copies[material_key]
        safe_name = f"BMF_MATERIAL_{index:03d}_{part.name}"
        scene.add_geometry(mesh, geom_name=safe_name, node_name=safe_name)

    if not scene.geometry:
        raise ValueError("A material preview needs at least one mesh piece.")
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(scene.export(file_type="glb"))
    return path
