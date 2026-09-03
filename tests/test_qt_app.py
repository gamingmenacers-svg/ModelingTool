from __future__ import annotations

import os
import json
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from bannerlord_model_forge.qt_app import ForgeStudio


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
