from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .blender_backend import extract_skeleton_data


def load_bannerlord_skeleton(skeleton_fbx: Path, cache_root: Path) -> tuple[Path, int]:
    """Extract and cache the official local Bannerlord rest-pose armature."""
    source = skeleton_fbx.expanduser().resolve()
    stat = source.stat()
    identity = f"{source}|{stat.st_size}|{stat.st_mtime_ns}|scale=100".encode("utf-8")
    cache_key = hashlib.sha256(identity).hexdigest()[:16]
    data_path = cache_root.expanduser().resolve() / f"human-skeleton-{cache_key}.json"
    if not data_path.is_file():
        extract_skeleton_data(source, data_path, scale=100.0)
    payload = json.loads(data_path.read_text(encoding="utf-8"))
    bone_count = int(payload.get("bone_count", len(payload.get("bones", []))))
    if bone_count < 1:
        raise RuntimeError("Bannerlord's skeleton FBX did not contain any bones.")
    return data_path, bone_count
