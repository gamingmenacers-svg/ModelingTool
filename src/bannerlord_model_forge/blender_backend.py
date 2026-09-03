from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class BlenderStatus:
    found: bool
    executable: str | None
    note: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def detect_blender() -> BlenderStatus:
    candidates: list[str] = []
    configured = os.environ.get("BMF_BLENDER")
    if configured:
        candidates.append(configured)
    on_path = shutil.which("blender")
    if on_path:
        candidates.append(on_path)
    program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
    candidates.extend(str(path) for path in sorted(program_files.glob("Blender Foundation/Blender */blender.exe"), reverse=True))
    for candidate in candidates:
        path = Path(candidate).expanduser()
        if path.is_file():
            return BlenderStatus(True, str(path.resolve()), "Blender can be used for FBX conversion and final skinned export.")
    return BlenderStatus(
        False,
        None,
        "Blender was not found. Native OBJ/GLB inspection works; FBX import and final skinned FBX export remain unavailable.",
    )


def convert_with_blender(
    source: Path,
    destination: Path,
    split_loose: bool = False,
    target_faces: int | None = None,
) -> Path:
    status = detect_blender()
    if not status.found or not status.executable:
        raise RuntimeError(status.note)
    bridge = Path(__file__).with_name("blender_bridge.py")
    destination.parent.mkdir(parents=True, exist_ok=True)
    command = [
        status.executable,
        "--background",
        "--factory-startup",
        "--python",
        str(bridge),
        "--",
        "--input",
        str(source.resolve()),
        "--output",
        str(destination.resolve()),
    ]
    if split_loose:
        command.append("--split-loose")
    if target_faces is not None:
        command.extend(("--target-faces", str(max(4, int(target_faces)))))
    completed = subprocess.run(command, capture_output=True, text=True, timeout=600, check=False)
    if completed.returncode != 0 or not destination.is_file():
        detail = (completed.stderr or completed.stdout)[-4000:]
        raise RuntimeError(f"Blender conversion failed: {detail.strip()}")
    return destination


def export_skinned_fbx(
    source: Path,
    skeleton_fbx: Path,
    weights_json: Path,
    destination: Path,
    bannerlord_unit_scale: bool = False,
) -> Path:
    status = detect_blender()
    if not status.found or not status.executable:
        raise RuntimeError(status.note)
    bridge = Path(__file__).with_name("blender_bridge.py")
    destination.parent.mkdir(parents=True, exist_ok=True)
    command = [
        status.executable,
        "--background",
        "--factory-startup",
        "--python",
        str(bridge),
        "--",
        "--input",
        str(source.resolve()),
        "--skeleton",
        str(skeleton_fbx.resolve()),
        "--weights",
        str(weights_json.resolve()),
        "--output",
        str(destination.resolve()),
    ]
    if bannerlord_unit_scale:
        command.append("--bannerlord-unit-scale")
    completed = subprocess.run(command, capture_output=True, text=True, timeout=600, check=False)
    if completed.returncode != 0 or not destination.is_file():
        detail = (completed.stderr or completed.stdout)[-4000:]
        raise RuntimeError(f"Blender skinned export failed: {detail.strip()}")
    return destination


def render_skeleton_overlay(
    source: Path,
    skeleton_fbx: Path,
    destination: Path,
    bannerlord_unit_scale: bool = False,
) -> tuple[Path, Path]:
    status = detect_blender()
    if not status.found or not status.executable:
        raise RuntimeError(status.note)
    renderer = Path(__file__).with_name("blender_skeleton_preview.py")
    destination.parent.mkdir(parents=True, exist_ok=True)
    command = [
        status.executable,
        "--background",
        "--factory-startup",
        "--python",
        str(renderer),
        "--",
        "--input",
        str(source.resolve()),
        "--skeleton",
        str(skeleton_fbx.resolve()),
        "--output",
        str(destination.resolve()),
    ]
    if bannerlord_unit_scale:
        command.append("--bannerlord-unit-scale")
    completed = subprocess.run(command, capture_output=True, text=True, timeout=600, check=False)
    if completed.returncode != 0 or not destination.is_file():
        detail = (completed.stderr or completed.stdout)[-4000:]
        raise RuntimeError(f"Blender skeleton preview failed: {detail.strip()}")
    data_path = destination.with_suffix(".json")
    if not data_path.is_file():
        raise RuntimeError("Blender rendered the skeleton preview but did not write its viewport data.")
    return destination, data_path


def extract_skeleton_data(
    skeleton_fbx: Path,
    destination: Path,
    scale: float = 1.0,
) -> Path:
    """Extract exact rest-pose bones from a local FBX into viewport JSON."""
    status = detect_blender()
    if not status.found or not status.executable:
        raise RuntimeError(status.note)
    extractor = Path(__file__).with_name("blender_skeleton_data.py")
    destination.parent.mkdir(parents=True, exist_ok=True)
    command = [
        status.executable,
        "--background",
        "--factory-startup",
        "--python",
        str(extractor),
        "--",
        "--skeleton",
        str(skeleton_fbx.resolve()),
        "--output",
        str(destination.resolve()),
        "--scale",
        str(scale),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=300, check=False)
    if completed.returncode != 0 or not destination.is_file():
        detail = (completed.stderr or completed.stdout)[-4000:]
        raise RuntimeError(f"Skeleton extraction failed: {detail.strip()}")
    return destination
