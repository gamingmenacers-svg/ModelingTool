from __future__ import annotations

from pathlib import Path

import numpy as np
import trimesh
from PIL import Image, ImageDraw


BG = (20, 24, 32)
EDGE = (32, 40, 52)
ACCENT = np.asarray((78, 164, 255), dtype=float)


def _rotation() -> np.ndarray:
    yaw = np.radians(32.0)
    pitch = np.radians(-18.0)
    ry = np.asarray([[np.cos(yaw), 0, np.sin(yaw)], [0, 1, 0], [-np.sin(yaw), 0, np.cos(yaw)]])
    rx = np.asarray([[1, 0, 0], [0, np.cos(pitch), -np.sin(pitch)], [0, np.sin(pitch), np.cos(pitch)]])
    return rx @ ry


def render_preview(mesh: trimesh.Trimesh, path: Path, title: str, size: int = 720) -> None:
    canvas = Image.new("RGB", (size, size), BG)
    draw = ImageDraw.Draw(canvas)
    if not len(mesh.faces):
        draw.text((24, 24), f"{title}\nNo faces", fill="white")
        canvas.save(path)
        return
    vertices = np.asarray(mesh.vertices, dtype=float)
    center = (mesh.bounds[0] + mesh.bounds[1]) / 2.0
    centered = vertices - center
    extents = np.ptp(centered, axis=0)
    up_axis = int(np.argmax(extents))
    remaining = [axis for axis in range(3) if axis != up_axis]
    remaining.sort(key=lambda axis: extents[axis], reverse=True)
    aligned = centered[:, [remaining[0], up_axis, remaining[1]]]
    rotated = aligned @ _rotation().T
    span = max(float(np.ptp(rotated[:, 0])), float(np.ptp(rotated[:, 1])), 1e-9)
    scale = (size * 0.78) / span
    points = np.empty((len(rotated), 2), dtype=float)
    points[:, 0] = rotated[:, 0] * scale + size / 2
    points[:, 1] = -rotated[:, 1] * scale + size / 2 + 12

    faces = np.asarray(mesh.faces, dtype=int)
    if len(faces) > 18_000:
        faces = faces[np.linspace(0, len(faces) - 1, 18_000).astype(int)]
    depth = rotated[faces][:, :, 2].mean(axis=1)
    order = np.argsort(depth)
    tri3 = rotated[faces]
    normals = np.cross(tri3[:, 1] - tri3[:, 0], tri3[:, 2] - tri3[:, 0])
    norm = np.linalg.norm(normals, axis=1)
    norm[norm == 0] = 1
    normals /= norm[:, None]
    light = np.asarray((-0.4, 0.6, 0.7))
    brightness = np.clip(0.32 + 0.68 * np.abs(normals @ light), 0.22, 1.0)
    for index in order:
        polygon = [tuple(points[v]) for v in faces[index]]
        color = tuple(np.clip(ACCENT * brightness[index], 0, 255).astype(int))
        draw.polygon(polygon, fill=color, outline=EDGE)
    draw.rounded_rectangle((16, 16, 300, 76), radius=10, fill=(9, 12, 18))
    draw.text((30, 27), title, fill=(245, 248, 252))
    draw.text((30, 49), f"{len(mesh.vertices):,} vertices  •  {len(mesh.faces):,} triangles", fill=(165, 178, 196))
    path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(path, format="PNG", optimize=True)
