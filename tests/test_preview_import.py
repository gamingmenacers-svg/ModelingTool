from __future__ import annotations

from pathlib import Path

from bannerlord_model_forge.preview_import import load_preview_mesh
from bannerlord_model_forge.sample import create_sample


def test_native_preview_loads_without_conversion(tmp_path: Path) -> None:
    source = create_sample(tmp_path / "preview.glb")

    mesh, displayed_path = load_preview_mesh(source, tmp_path / "cache")

    assert displayed_path == source.resolve()
    assert len(mesh.vertices) > 0
    assert len(mesh.faces) > 0


def test_fbx_preview_uses_stable_cached_conversion(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "armour.fbx"
    source.write_bytes(b"synthetic test input")
    converted_source = create_sample(tmp_path / "converted-source.glb")
    conversions: list[tuple[Path, Path]] = []

    def fake_convert(input_path: Path, output_path: Path) -> Path:
        conversions.append((input_path, output_path))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(converted_source.read_bytes())
        return output_path

    monkeypatch.setattr("bannerlord_model_forge.preview_import.convert_with_blender", fake_convert)
    first_mesh, first_path = load_preview_mesh(source, tmp_path / "cache")
    second_mesh, second_path = load_preview_mesh(source, tmp_path / "cache")

    assert len(conversions) == 1
    assert first_path == second_path
    assert first_path.suffix == ".glb"
    assert len(first_mesh.vertices) == len(second_mesh.vertices) > 0
