from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from .blender_backend import convert_with_blender
from .mesh_io import MeshPart, combine_mesh_parts, load_mesh_parts


@dataclass
class PreviewAsset:
    source_path: Path
    display_path: Path
    parts: list[MeshPart]

    def combined_mesh(self):
        return combine_mesh_parts(self.parts)


def load_preview_asset(source: Path, cache_root: Path) -> PreviewAsset:
    """Load a model as named selectable pieces while retaining UV materials."""
    source = source.expanduser().resolve()
    display_path = source
    if source.suffix.lower() == ".fbx":
        stat = source.stat()
        identity = f"{source}|{stat.st_size}|{stat.st_mtime_ns}|split-loose-v2".encode("utf-8")
        cache_key = hashlib.sha256(identity).hexdigest()[:16]
        display_path = cache_root.expanduser().resolve() / f"{source.stem}-{cache_key}.glb"
        if not display_path.is_file():
            convert_with_blender(source, display_path, split_loose=True)
    parts, _context = load_mesh_parts(display_path)
    generated_pieces: list[tuple[int, MeshPart]] = []
    named_parts: list[MeshPart] = []
    for part in parts:
        marker = part.name.upper().rpartition("BMF_PIECE_")[2]
        if marker.isdigit():
            number = int(marker)
            part.name = f"Armour piece {number:02d}"
            generated_pieces.append((number, part))
        else:
            named_parts.append(part)
    if generated_pieces:
        generated_pieces.sort(key=lambda value: value[0])
        parts = [part for _number, part in generated_pieces] + named_parts
    return PreviewAsset(source, display_path, parts)


def load_preview_mesh(source: Path, cache_root: Path):
    """Load a native mesh or convert an FBX into an isolated, reusable GLB preview."""
    asset = load_preview_asset(source, cache_root)
    return asset.combined_mesh(), asset.display_path
