from __future__ import annotations

import json
from pathlib import Path

from bannerlord_model_forge.skeleton_import import load_bannerlord_skeleton


def test_official_skeleton_extraction_is_cached(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "human_skeleton.fbx"
    source.write_bytes(b"synthetic skeleton")
    extractions: list[tuple[Path, Path, float]] = []

    def fake_extract(input_path: Path, output_path: Path, scale: float = 1.0) -> Path:
        extractions.append((input_path, output_path, scale))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(
                {
                    "bone_count": 2,
                    "bones": [
                        {"name": "root_0", "head": [0, 0, 0], "tail": [0, 0, 1], "parent": None},
                        {"name": "spine_1", "head": [0, 0, 1], "tail": [0, 0, 2], "parent": "root_0"},
                    ],
                }
            ),
            encoding="utf-8",
        )
        return output_path

    monkeypatch.setattr("bannerlord_model_forge.skeleton_import.extract_skeleton_data", fake_extract)
    first_path, first_count = load_bannerlord_skeleton(source, tmp_path / "cache")
    second_path, second_count = load_bannerlord_skeleton(source, tmp_path / "cache")

    assert first_path == second_path
    assert first_count == second_count == 2
    assert len(extractions) == 1
    assert extractions[0][2] == 100.0
