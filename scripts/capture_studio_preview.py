from __future__ import annotations

import sys
import os
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from bannerlord_model_forge.blender_backend import convert_with_blender
from bannerlord_model_forge.preview_import import load_preview_asset
from bannerlord_model_forge.qt_app import APP_STYLE, ForgeStudio
from bannerlord_model_forge.sample import create_sample
from bannerlord_model_forge.game_install import inspect_game_install
from bannerlord_model_forge.skeleton_import import load_bannerlord_skeleton


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    work = project_root / "work" / "preview-capture"
    capture_model = os.environ.get("BMF_CAPTURE_MODEL", "").strip()
    output = project_root / "outputs" / ("piece-selection-preview.png" if capture_model else "gpu-studio-preview.png")
    skeleton_output = project_root / "outputs" / "official-skeleton-preview.png"
    work.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)

    if capture_model:
        fbx = Path(capture_model).expanduser().resolve()
    else:
        native = create_sample(work / "generated_fit_test.glb")
        fbx = convert_with_blender(native, work / "generated_fit_test.fbx")
    asset = load_preview_asset(fbx, project_root / "work" / "preview-cache")
    game = inspect_game_install()
    if not game.human_skeleton_path:
        raise RuntimeError("Bannerlord human_skeleton.fbx was not found")
    skeleton_data, bone_count = load_bannerlord_skeleton(Path(game.human_skeleton_path), work / "skeleton-cache")

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLE)
    window = ForgeStudio(load_official_skeleton=False)
    window.resize(1520, 940)
    window.show()
    window.source_path = fbx
    window.drop_card.set_path(fbx)
    window.skeleton_data_path = skeleton_data
    window._show_source_preview(asset)
    window.skeleton_status.setText(f"LIVE • {bone_count} OFFICIAL BONES")
    window.skeleton_detail.setText("Exact rest hierarchy from the installed human_skeleton.fbx; referenced read-only.")
    window._refresh_scene_list()
    window._log(f"FBX displayed with {bone_count} exact bones from the installed Bannerlord rest rig.")
    if len(asset.parts) > 1:
        requested_row = int(os.environ.get("BMF_CAPTURE_ROW", "3"))
        selected_row = min(max(0, requested_row), len(asset.parts) - 1)
        window._select_part_from_viewport(selected_row)
        if os.environ.get("BMF_CAPTURE_AUTOFIT") == "1":
            window._auto_fit_selected_part()
        window._frame_selected_part()
        if os.environ.get("BMF_CAPTURE_ISOLATE") == "1":
            for index in range(len(asset.parts)):
                window.viewport.set_part_visible(index, index == selected_row)

    def capture() -> None:
        pixmap = window.grab()
        if not pixmap.save(str(output), "PNG"):
            app.exit(1)
            return
        window.source_path = None
        window.source_asset = None
        window.preview_asset = None
        window.drop_card.path_label.setText("Drop FBX, GLB, OBJ, PLY or STL")
        window.viewport.clear()
        window.viewport.set_skeleton_data(skeleton_data, window.piece_combo.currentData())
        window.job_label.setText("OFFICIAL RIG LINKED • READY")
        window._refresh_scene_list()

        def capture_skeleton() -> None:
            if not window.grab().save(str(skeleton_output), "PNG"):
                app.exit(1)
                return
            window.close()
            app.exit(0)

        QTimer.singleShot(500, capture_skeleton)

    QTimer.singleShot(1800, capture)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
