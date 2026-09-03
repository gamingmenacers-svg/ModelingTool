from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QTimer, QUrl, Signal
from PySide6.QtQuick3D import QQuick3D
from PySide6.QtQuickWidgets import QQuickWidget


def _resource_path(name: str) -> Path:
    bundle_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    bundled = bundle_root / "bannerlord_model_forge" / name
    return bundled if bundled.is_file() else Path(__file__).with_name(name)


class MaterialViewport(QQuickWidget):
    """Qt Quick 3D's maintained glTF renderer for trustworthy material review."""

    render_error = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFormat(QQuick3D.idealSurfaceFormat())
        self.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)
        self.statusChanged.connect(self._status_changed)
        self.setSource(QUrl.fromLocalFile(str(_resource_path("material_viewport.qml").resolve())))
        self._source_path: Path | None = None

    @property
    def source_path(self) -> Path | None:
        return self._source_path

    def set_model(self, path: Path | None, *, base_color_only: bool = True) -> None:
        self._source_path = path.expanduser().resolve() if path is not None else None
        root = self.rootObject()
        if root is None:
            return
        root.setProperty("baseColorOnly", base_color_only)
        # Clear first so overwriting a cached preview at the same path still reloads.
        root.setProperty("modelSource", QUrl())
        if self._source_path is not None:
            source_url = QUrl.fromLocalFile(str(self._source_path))
            QTimer.singleShot(0, lambda: self._set_source_url(source_url))

    def set_base_color_only(self, enabled: bool) -> None:
        root = self.rootObject()
        if root is not None:
            root.setProperty("baseColorOnly", enabled)

    def _set_source_url(self, source_url: QUrl) -> None:
        root = self.rootObject()
        if root is not None:
            root.setProperty("modelSource", source_url)

    def _status_changed(self, status: QQuickWidget.Status) -> None:
        if status == QQuickWidget.Status.Error:
            message = "\n".join(error.toString() for error in self.errors())
            self.render_error.emit(message or "Qt Quick 3D material viewport failed to initialize.")
