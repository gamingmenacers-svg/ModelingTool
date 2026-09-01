from __future__ import annotations

from pathlib import Path

import numpy as np
import trimesh

from .mesh_io import export_mesh


def _limb(start: tuple[float, float, float], end: tuple[float, float, float], radius: float) -> trimesh.Trimesh:
    start_point = np.asarray(start, dtype=float)
    end_point = np.asarray(end, dtype=float)
    direction = end_point - start_point
    transform = trimesh.geometry.align_vectors([0.0, 0.0, 1.0], direction)
    transform[:3, 3] = (start_point + end_point) * 0.5
    return trimesh.creation.cylinder(radius=radius, height=float(np.linalg.norm(direction)), sections=32, transform=transform)


def create_sample(path: Path) -> Path:
    """Create an original stylised armoured mannequin; no game assets are used."""
    parts: list[trimesh.Trimesh] = []

    head = trimesh.creation.icosphere(subdivisions=3, radius=1.0)
    head.apply_scale((0.115, 0.105, 0.145))
    head.apply_translation((0.0, 0.0, 1.70))
    parts.append(head)
    neck = trimesh.creation.cylinder(radius=0.065, height=0.13, sections=32)
    neck.apply_translation((0.0, 0.0, 1.52))
    parts.append(neck)

    torso = trimesh.creation.icosphere(subdivisions=3, radius=1.0)
    torso.apply_scale((0.31, 0.16, 0.38))
    torso.apply_translation((0.0, 0.0, 1.25))
    parts.append(torso)
    pelvis = trimesh.creation.icosphere(subdivisions=2, radius=1.0)
    pelvis.apply_scale((0.24, 0.14, 0.19))
    pelvis.apply_translation((0.0, 0.0, 0.91))
    parts.append(pelvis)

    for side in (-1.0, 1.0):
        shoulder = (0.30 * side, 0.0, 1.43)
        elbow = (0.43 * side, 0.0, 1.15)
        wrist = (0.40 * side, 0.005, 0.91)
        parts.extend((_limb(shoulder, elbow, 0.082), _limb(elbow, wrist, 0.064)))
        hand = trimesh.creation.icosphere(subdivisions=2, radius=1.0)
        hand.apply_scale((0.060, 0.050, 0.090))
        hand.apply_translation(wrist)
        parts.append(hand)

        hip = (0.13 * side, 0.0, 0.83)
        knee = (0.15 * side, 0.0, 0.48)
        ankle = (0.145 * side, 0.0, 0.12)
        parts.extend((_limb(hip, knee, 0.095), _limb(knee, ankle, 0.074)))
        foot = trimesh.creation.box(extents=(0.14, 0.27, 0.095))
        foot.apply_translation((0.145 * side, 0.065, 0.055))
        parts.append(foot)

    # Original armour plates layered over the neutral mannequin proportions.
    breastplate = trimesh.creation.icosphere(subdivisions=3, radius=1.0)
    breastplate.apply_scale((0.325, 0.177, 0.32))
    breastplate.apply_translation((0.0, -0.005, 1.29))
    parts.append(breastplate)
    waist = trimesh.creation.cylinder(radius=0.255, height=0.24, sections=64)
    waist.apply_scale((1.0, 0.58, 1.0))
    waist.apply_translation((0.0, 0.0, 0.96))
    parts.append(waist)
    for side in (-1.0, 1.0):
        pauldron = trimesh.creation.icosphere(subdivisions=2, radius=1.0)
        pauldron.apply_scale((0.145, 0.19, 0.11))
        pauldron.apply_translation((0.31 * side, 0.0, 1.45))
        parts.append(pauldron)

    mesh = trimesh.util.concatenate(parts)
    mesh.vertices[:, 1] += 0.006 * np.sin(mesh.vertices[:, 0] * 24.0)
    mesh.metadata["source_material_names"] = ["training_steel"]
    mesh.metadata["texture_references"] = []
    export_mesh(mesh, path)
    return path
