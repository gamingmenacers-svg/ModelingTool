from __future__ import annotations

import os
import json
from pathlib import Path

import trimesh
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from bannerlord_model_forge.qt_app import ForgeStudio
from bannerlord_model_forge.mesh_io import MeshPart
from bannerlord_model_forge.preview_import import PreviewAsset


def test_modern_studio_constructs_and_exposes_comparison_mode(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    window = ForgeStudio(load_official_skeleton=False)
    try:
        assert window.windowTitle() == "Bannerlord Model Forge — Rigging Studio"
        assert window.viewport.compare_mode is False
        window.mode_compare.setChecked(True)
        window._toggle_compare(True)
        assert window.viewport.compare_mode is True
        assert window.mode_single.isChecked() is False

        skeleton = tmp_path / "official-rig.json"
        skeleton.write_text(
            json.dumps(
                {
                    "bones": [
                        {"name": "root_0", "head": [0, 0, 0], "tail": [0, 0, 0.1], "parent": None},
                        {"name": "spine_1", "head": [0, 0, 1], "tail": [0, 0, 1.2], "parent": "root_0"},
                    ]
                }
            ),
            encoding="utf-8",
        )
        window._skeleton_ready((skeleton, 2))
        assert window.skeleton_data_path == skeleton
        assert len(window.viewport.skeleton) == 2
        assert window.skeleton_status.text() == "LIVE • 2 OFFICIAL BONES"
    finally:
        window.close()
        app.processEvents()


def test_scene_outliner_selects_removes_and_restores_individual_parts(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    window = ForgeStudio(load_official_skeleton=False)
    source = tmp_path / "armour-set.glb"
    source.write_bytes(b"test source remains untouched")
    parts = [
        MeshPart("Chest", trimesh.creation.box()),
        MeshPart("Pauldron", trimesh.creation.icosphere(subdivisions=1)),
    ]
    asset = PreviewAsset(source.resolve(), source.resolve(), parts)
    try:
        window.source_path = source.resolve()
        window.source_asset = asset
        window.preview_asset = asset
        window.viewport.set_parts(parts)
        window._refresh_scene_list()
        window.asset_list.item(1).setSelected(True)

        assert window._selected_part_indices() == [1]
        assert window.viewport.selected_part == 1
        window._solo_selected_part()
        assert window.viewport.hidden_parts == {0}
        window._show_working_set()
        assert not window.viewport.hidden_parts
        window._remove_selected_parts()
        assert window.removed_parts == {1}
        assert window.viewport.hidden_parts == {1}
        assert source.read_bytes() == b"test source remains untouched"

        window._restore_all_parts()
        assert not window.removed_parts
        assert not window.viewport.hidden_parts
    finally:
        window.close()
        app.processEvents()
