from __future__ import annotations

import math
import logging

import numpy as np
import trimesh

from .mesh_io import clone_mesh
from .models import QualityMetrics


def clean_mesh(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    """Apply deterministic topology cleanup without altering the source object."""
    result = clone_mesh(mesh)
    if len(result.faces):
        result.update_faces(result.nondegenerate_faces(height=1e-12))
        result.update_faces(result.unique_faces())
    result.remove_unreferenced_vertices()
    result.merge_vertices(digits_vertex=8, merge_tex=False, merge_norm=False)
    result.remove_unreferenced_vertices()
    if len(result.faces):
        trimesh.repair.fix_normals(result, multibody=True)
    result.metadata.update(mesh.metadata)
    return result


def simplify_mesh(mesh: trimesh.Trimesh, target_faces: int) -> trimesh.Trimesh:
    target_faces = max(4, int(target_faces))
    if len(mesh.faces) <= target_faces:
        return clone_mesh(mesh)
    simplified = mesh.simplify_quadric_decimation(face_count=target_faces, aggression=5)
    simplified.metadata.update(mesh.metadata)
    if len(simplified.faces):
        trimesh.repair.fix_normals(simplified, multibody=True)
    return simplified


def make_lods(mesh: trimesh.Trimesh, ratios: tuple[float, ...]) -> list[trimesh.Trimesh]:
    lods: list[trimesh.Trimesh] = []
    previous = len(mesh.faces)
    for ratio in ratios:
        target = max(4, min(previous - 1, int(round(len(mesh.faces) * ratio))))
        if target >= previous:
            continue
        lod = simplify_mesh(mesh, target)
        if len(lod.faces) >= previous:
            continue
        lods.append(lod)
        previous = len(lod.faces)
    return lods


def _nearest(source: np.ndarray, target: np.ndarray, chunk_size: int = 256) -> tuple[np.ndarray, np.ndarray]:
    distances: list[np.ndarray] = []
    indices: list[np.ndarray] = []
    for start in range(0, len(source), chunk_size):
        block = source[start : start + chunk_size]
        delta = block[:, None, :] - target[None, :, :]
        squared = np.einsum("ijk,ijk->ij", delta, delta)
        idx = squared.argmin(axis=1)
        indices.append(idx)
        distances.append(np.sqrt(squared[np.arange(len(block)), idx]))
    return np.concatenate(distances), np.concatenate(indices)


def quality_metrics(before: trimesh.Trimesh, after: trimesh.Trimesh) -> QualityMetrics:
    if not len(before.vertices) or not len(after.vertices):
        return QualityMetrics(0.0, 0.0, None, "unknown")
    sample_idx = np.linspace(0, len(before.vertices) - 1, min(1500, len(before.vertices))).astype(int)
    sample = np.asarray(before.vertices)[sample_idx]
    target = np.asarray(after.vertices)
    distance, nearest = _nearest(sample, target)
    diagonal = max(float(np.linalg.norm(before.extents)), 1e-12)
    rms = math.sqrt(float(np.mean(distance**2))) / diagonal * 100.0
    maximum = float(distance.max()) / diagonal * 100.0

    mean_angle: float | None = None
    if len(before.vertices) <= 75_000:
        try:
            normal_logger = logging.getLogger("trimesh.util")
            previous_level = normal_logger.level
            normal_logger.setLevel(logging.ERROR)
            try:
                n1 = np.asarray(before.vertex_normals)[sample_idx]
                n2 = np.asarray(after.vertex_normals)[nearest]
            finally:
                normal_logger.setLevel(previous_level)
            dots = np.clip(np.einsum("ij,ij->i", n1, n2), -1.0, 1.0)
            mean_angle = float(np.degrees(np.arccos(dots)).mean())
        except Exception:
            pass
    if maximum < 0.35 and (mean_angle is None or mean_angle < 8):
        visible = "low"
    elif maximum < 1.5 and (mean_angle is None or mean_angle < 25):
        visible = "moderate"
    else:
        visible = "high"
    return QualityMetrics(
        nearest_vertex_rms_percent_diagonal=round(rms, 4),
        nearest_vertex_max_percent_diagonal=round(maximum, 4),
        mean_normal_change_degrees=round(mean_angle, 3) if mean_angle is not None else None,
        visible_loss=visible,
    )
