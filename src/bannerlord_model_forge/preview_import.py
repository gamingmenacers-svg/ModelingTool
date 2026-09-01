from __future__ import annotations

import hashlib
from pathlib import Path

from .blender_backend import convert_with_blender
from .mesh_io import load_mesh


def load_preview_mesh(source: Path, cache_root: Path):
    """Load a native mesh or convert an FBX into an isolated, reusable GLB preview."""
    source = source.expanduser().resolve()
    if source.suffix.lower() != ".fbx":
        mesh, _context = load_mesh(source)
        return mesh, source

    stat = source.stat()
    identity = f"{source}|{stat.st_size}|{stat.st_mtime_ns}".encode("utf-8")
    cache_key = hashlib.sha256(identity).hexdigest()[:16]
    converted = cache_root.expanduser().resolve() / f"{source.stem}-{cache_key}.glb"
    if not converted.is_file():
        convert_with_blender(source, converted)
    mesh, _context = load_mesh(converted)
    return mesh, converted
