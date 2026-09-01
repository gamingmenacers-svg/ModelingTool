from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from bannerlord_model_forge.blender_backend import convert_with_blender
from bannerlord_model_forge.preview_import import load_preview_mesh
from bannerlord_model_forge.qt_app import APP_STYLE, ForgeStudio
from bannerlord_model_forge.sample import create_sample


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    work = project_root / "work" / "preview-capture"
    output = project_root / "outputs" / "gpu-studio-preview.png"
    work.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)

    native = create_sample(work / "forge_armour.glb")
    fbx = convert_with_blender(native, work / "forge_armour.fbx")
    mesh, _preview_path = load_preview_mesh(fbx, work / "cache")

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLE)
    window = ForgeStudio()
    window.resize(1520, 940)
    window.show()
    window.source_path = fbx
    window.drop_card.set_path(fbx)
    window._show_source_preview((mesh, fbx.name))
    window._log("FBX converted read-only and displayed in the GPU viewport.")

    def capture() -> None:
        pixmap = window.grab()
        if not pixmap.save(str(output), "PNG"):
            app.exit(1)
            return
        window.close()
        app.exit(0)

    QTimer.singleShot(1800, capture)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
