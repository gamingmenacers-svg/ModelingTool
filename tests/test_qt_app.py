from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from bannerlord_model_forge.qt_app import ForgeStudio


def test_modern_studio_constructs_and_exposes_comparison_mode() -> None:
    app = QApplication.instance() or QApplication([])
    window = ForgeStudio()
    try:
        assert window.windowTitle() == "Bannerlord Model Forge — Rigging Studio"
        assert window.viewport.compare_mode is False
        window.mode_compare.setChecked(True)
        window._toggle_compare(True)
        assert window.viewport.compare_mode is True
        assert window.mode_single.isChecked() is False
    finally:
        window.close()
        app.processEvents()
