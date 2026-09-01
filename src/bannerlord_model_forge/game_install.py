from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from .config import GAME_ROOT


@dataclass(frozen=True)
class GameInstallInfo:
    root: str
    found: bool
    version: str | None
    editor_found: bool
    human_skeleton_found: bool
    human_skeleton_path: str | None
    note: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def inspect_game_install(root: Path = GAME_ROOT) -> GameInstallInfo:
    """Read a small, allowlisted set of installation metadata; never writes there."""
    package_info = root / "package_info.txt"
    editor = root / "bin" / "Win64_Shipping_wEditor"
    skeleton = root / "modding_resources" / "skeletons" / "human_skeleton.fbx"
    version = None
    if package_info.is_file():
        for line in package_info.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("Environment:") and "@" in line:
                version = line.rsplit("@", 1)[-1].strip()
                break
    return GameInstallInfo(
        root=str(root),
        found=root.is_dir(),
        version=version,
        editor_found=editor.is_dir(),
        human_skeleton_found=skeleton.is_file(),
        human_skeleton_path=str(skeleton) if skeleton.is_file() else None,
        note="Read-only inspection; no game files are copied or changed.",
    )
