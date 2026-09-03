from __future__ import annotations

import json
import os
import re
import sys
import threading
from pathlib import Path

import numpy as np
from PySide6.QtCore import QObject, QPoint, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QDragEnterEvent, QDropEvent, QFont, QIcon, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .auto_fit import auto_fit_to_bannerlord
from .blender_backend import detect_blender
from .config import BONE_REGION_PATTERNS, PRESETS, project_root
from .game_install import inspect_game_install
from .gpu_viewport import RigViewport
from .material_compiler import inspect_source_material
from .mesh_io import MeshPart, export_mesh, load_mesh
from .pipeline import run_pipeline
from .preview_import import PreviewAsset, load_preview_asset
from .sample import create_sample
from .skeleton_import import load_bannerlord_skeleton


APP_STYLE = """
* {
    font-family: "Segoe UI Variable", "Segoe UI";
    font-size: 13px;
    color: #dce3ec;
}
QMainWindow, QWidget#Root { background: #090d13; }
QFrame#TopBar { background: #101620; border-bottom: 1px solid #263244; }
QFrame#LeftRail, QFrame#Inspector { background: #0e141d; }
QFrame#LeftRail { border-right: 1px solid #252d3a; }
QFrame#Inspector { border-left: 1px solid #252d3a; }
QFrame#Card { background: #141c27; border: 1px solid #293649; border-radius: 11px; }
QFrame#DropCard { background: #111a26; border: 1px dashed #3b5878; border-radius: 12px; }
QFrame#DropCard[active="true"] { background: #17273a; border: 1px solid #5aa9ff; }
QFrame#StatusGood { background: #13271f; border: 1px solid #25523f; border-radius: 13px; }
QFrame#StatusWarn { background: #2b2416; border: 1px solid #604b25; border-radius: 13px; }
QLabel#Title { color: #f5f7fa; font-size: 17px; font-weight: 650; }
QLabel#Section { color: #8e9aaa; font-size: 10px; font-weight: 700; letter-spacing: 1.4px; }
QLabel#Muted { color: #8d99a9; }
QLabel#Value { color: #f2f5f8; font-weight: 600; }
QLabel#Accent { color: #62adff; font-weight: 650; }
QLabel#Good { color: #6ed6a5; }
QLabel#Warning { color: #f5bd68; }
QLabel#Error { color: #ff7f86; font-weight: 650; }
QPushButton, QToolButton {
    background: #1b2330; border: 1px solid #303b4d; border-radius: 6px;
    padding: 8px 12px; color: #dce3ec;
}
QPushButton:hover, QToolButton:hover { background: #253044; border-color: #506178; }
QPushButton:pressed, QToolButton:pressed { background: #18202c; }
QPushButton:disabled { color: #596474; background: #151a22; border-color: #232a35; }
QPushButton#Primary {
    background: #398ceb; border: 1px solid #62adff; color: white;
    padding: 11px 16px; border-radius: 7px; font-weight: 700;
}
QPushButton#Primary:hover { background: #4b9bf3; }
QPushButton#Quiet { background: transparent; border-color: #303946; }
QToolButton:checked { background: #203b5b; border-color: #4e9cf0; color: #8bc4ff; }
QLineEdit, QComboBox, QSpinBox {
    background: #0e131b; border: 1px solid #303a49; border-radius: 6px;
    padding: 8px; selection-background-color: #357fcf;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border-color: #559fe9; }
QComboBox::drop-down { border: none; width: 24px; }
QComboBox QAbstractItemView { background: #171d27; border: 1px solid #344052; selection-background-color: #2a537c; }
QTabWidget::pane { border: none; background: #11161f; }
QTabBar::tab { background: transparent; color: #8290a2; padding: 11px 15px; border-bottom: 2px solid transparent; }
QTabBar::tab:selected { color: #ecf3fa; border-bottom-color: #55a7ff; }
QScrollArea { border: none; background: #11161f; }
QScrollArea > QWidget > QWidget { background: #11161f; }
QScrollBar:vertical { background: #10151d; width: 8px; }
QScrollBar::handle:vertical { background: #354052; border-radius: 4px; min-height: 32px; }
QTextEdit#Console { background: #0a0d12; border: none; color: #9eabbc; font-family: "Cascadia Mono"; font-size: 11px; }
QListWidget { background: #0b1119; border: 1px solid #222e3e; border-radius: 8px; outline: none; padding: 5px; }
QListWidget::item { padding: 8px 6px; border-radius: 5px; }
QListWidget::item:selected { background: #1d2d42; color: #81bcfb; }
QToolTip { background: #171d27; color: #e7edf5; border: 1px solid #3a4659; padding: 6px; }
QProgressBar { background: #0d1219; border: 1px solid #2a3443; border-radius: 4px; height: 7px; text-align: center; }
QProgressBar::chunk { background: #4599ef; border-radius: 3px; }
QCheckBox::indicator { width: 16px; height: 16px; }
QSplitter::handle { background: #202733; }
"""


def section_label(text: str) -> QLabel:
    label = QLabel(text.upper())
    label.setObjectName("Section")
    return label


def muted(text: str, wrap: bool = False) -> QLabel:
    label = QLabel(text)
    label.setObjectName("Muted")
    label.setWordWrap(wrap)
    return label


def material_inspection_text(inspection) -> str:
    labels = (
        ("albedo", "Base colour"),
        ("normal", "Normal"),
        ("metallic_roughness", "Metal / roughness"),
        ("occlusion", "Ambient occlusion"),
        ("emissive", "Emissive"),
    )
    lines = ["DETECTED FROM FBX"]
    for key, label in labels:
        slot = inspection.source_slots[key]
        if slot.get("present"):
            lines.append(f"✓  {label}  {slot['width']}×{slot['height']}")
        else:
            lines.append(f"—  {label}  not supplied")
    lines.append("")
    lines.append("COMPILER DECISION")
    if inspection.source_slots["albedo"].get("present"):
        lines.append("✓  Preserve source pixels as _d")
    if inspection.source_slots["metallic_roughness"].get("present") or inspection.source_slots["occlusion"].get("present"):
        lines.append("✓  Pack source metallic / gloss / AO as _s")
    else:
        lines.append("i  Build _s from explicit conservative defaults")
    if inspection.authored_alpha_mode != "OPAQUE" and not inspection.meaningful_alpha:
        lines.append(f"✓  Alpha {inspection.authored_alpha_mode} → OPAQUE (image is fully opaque)")
    return "\n".join(lines)


def card(layout: QVBoxLayout | QHBoxLayout | None = None) -> QFrame:
    frame = QFrame()
    frame.setObjectName("Card")
    if layout is not None:
        frame.setLayout(layout)
    return frame


class DropCard(QFrame):
    file_selected = Signal(str)
    browse_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("DropCard")
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(122)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 16)
        layout.setSpacing(5)
        icon = QLabel("＋")
        icon.setStyleSheet("font-size: 24px; color: #62adff;")
        title = QLabel("Import armour or weapon")
        title.setObjectName("Value")
        self.path_label = muted("Drop FBX, GLB, OBJ, PLY or STL")
        layout.addWidget(icon, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(title, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self.path_label, alignment=Qt.AlignmentFlag.AlignHCenter)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self.browse_requested.emit()
        super().mousePressEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # type: ignore[override]
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setProperty("active", True)
            self.style().unpolish(self)
            self.style().polish(self)

    def dragLeaveEvent(self, event) -> None:  # type: ignore[override]
        self.setProperty("active", False)
        self.style().unpolish(self)
        self.style().polish(self)
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:  # type: ignore[override]
        self.setProperty("active", False)
        self.style().unpolish(self)
        self.style().polish(self)
        urls = event.mimeData().urls()
        if urls:
            self.file_selected.emit(urls[0].toLocalFile())
            event.acceptProposedAction()

    def set_path(self, path: Path) -> None:
        self.path_label.setText(path.name)
        self.path_label.setToolTip(str(path))


class LegacyRigViewport(QWidget):
    bone_options_changed = Signal(list, bool)
    statistics_changed = Signal(dict)

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumSize(560, 430)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.mesh = None
        self.skeleton: list[dict[str, object]] = []
        self.weights: list[dict[str, float]] = []
        self.weights_provisional = False
        self.focus_patterns: tuple[str, ...] = ()
        self.selected_bone = ""
        self.wireframe = False
        self.show_skeleton = True
        self.compare_mode = False
        self.yaw = 0.38
        self.pitch = -0.10
        self.zoom = 1.0
        self.last_mouse: QPoint | None = None
        self.label = "FITTING STAGE"
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(840, 620)

    def set_model(
        self,
        mesh,
        skeleton_path: Path | None = None,
        weights_path: Path | None = None,
        label: str = "Imported model",
        preset_key: str | None = None,
    ) -> None:
        self.mesh = mesh
        self.label = label.upper()
        self.skeleton = []
        if skeleton_path and skeleton_path.is_file():
            payload = json.loads(skeleton_path.read_text(encoding="utf-8"))
            self.skeleton = list(payload.get("bones", []))
        self.weights = []
        self.weights_provisional = False
        self.focus_patterns = (
            BONE_REGION_PATTERNS.get(PRESETS[preset_key].skeleton_region, ())
            if preset_key in PRESETS
            else ()
        )
        bones: list[str] = []
        if weights_path and weights_path.is_file():
            payload = json.loads(weights_path.read_text(encoding="utf-8"))
            self.weights = list(payload.get("weights", []))
            self.weights_provisional = bool(payload.get("provisional", False))
            bones = [str(name) for name in payload.get("bones", [])]
        self.selected_bone = ""
        self.bone_options_changed.emit(bones, self.weights_provisional)
        self.statistics_changed.emit(
            {
                "vertices": len(mesh.vertices),
                "triangles": len(mesh.faces),
                "bones": len(self.skeleton),
                "weights": bool(bones),
            }
        )
        self.set_view(0.38, -0.10)

    def clear(self) -> None:
        self.mesh = None
        self.skeleton = []
        self.weights = []
        self.update()

    def set_view(self, yaw: float, pitch: float) -> None:
        self.yaw, self.pitch, self.zoom = yaw, pitch, 1.0
        self.update()

    def set_selected_bone(self, name: str) -> None:
        self.selected_bone = "" if name.startswith("Weight heatmap") else name
        self.update()

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self.last_mouse = event.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        self.last_mouse = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if self.last_mouse is None:
            return
        point = event.position().toPoint()
        delta = point - self.last_mouse
        self.last_mouse = point
        self.yaw += delta.x() * 0.010
        self.pitch = float(np.clip(self.pitch + delta.y() * 0.010, -1.35, 1.35))
        self.update()

    def wheelEvent(self, event) -> None:  # type: ignore[override]
        self.zoom = float(np.clip(self.zoom * (1.12 if event.angleDelta().y() > 0 else 0.89), 0.35, 4.0))
        self.update()

    def paintEvent(self, _event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#090c11"))
        self._draw_stage(painter)
        if self.mesh is None or not len(self.mesh.faces):
            self._draw_empty(painter)
        else:
            self._draw_model(painter)
        self._draw_overlay(painter)

    def _draw_stage(self, painter: QPainter) -> None:
        width, height = self.width(), self.height()
        horizon = int(height * 0.40)
        painter.fillRect(0, 0, width, horizon, QColor("#111823"))
        painter.fillRect(0, horizon, width, height - horizon, QColor("#0d1118"))
        painter.setPen(QPen(QColor(44, 55, 69, 150), 1))
        for i in range(-14, 15):
            x_bottom = width / 2 + i * width / 14
            x_horizon = width / 2 + i * width / 100
            painter.drawLine(QPointF(x_horizon, horizon), QPointF(x_bottom, height))
        for row in range(15):
            t = row / 14
            y = horizon + (t * t) * (height - horizon)
            painter.drawLine(QPointF(0, y), QPointF(width, y))
        # Subtle alternating stage tiles, echoing TaleWorlds' visual-test floor.
        painter.setPen(Qt.PenStyle.NoPen)
        tile = max(38, width // 18)
        for y in range(horizon + tile, height + tile, tile):
            for x in range(-tile, width + tile, tile):
                if ((x // tile) + (y // tile)) % 2 == 0:
                    painter.fillRect(x, y, tile, tile, QColor(255, 255, 255, 5))
        painter.setPen(QPen(QColor("#283342"), 1))
        painter.drawLine(0, horizon, width, horizon)

    def _draw_empty(self, painter: QPainter) -> None:
        center = QPointF(self.width() / 2, self.height() / 2 - 30)
        painter.setPen(QPen(QColor("#38475b"), 2))
        painter.setBrush(QColor(18, 25, 35, 210))
        painter.drawRoundedRect(QRectF(center.x() - 160, center.y() - 80, 320, 160), 12, 12)
        painter.setPen(QColor("#7f8da0"))
        font = painter.font()
        font.setPointSize(12)
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.drawText(QRectF(center.x() - 145, center.y() - 45, 290, 28), Qt.AlignmentFlag.AlignCenter, "CHARACTER FITTING STAGE")
        painter.setPen(QColor("#657287"))
        font.setPointSize(9)
        font.setWeight(QFont.Weight.Normal)
        painter.setFont(font)
        painter.drawText(
            QRectF(center.x() - 135, center.y() - 3, 270, 50),
            Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
            "Import an armour piece, then select its slot to inspect fit, skeleton alignment and deformation weights.",
        )

    def _draw_model(self, painter: QPainter) -> None:
        source_vertices = np.asarray(self.mesh.vertices, dtype=float)
        source_faces = np.asarray(self.mesh.faces, dtype=int)
        extents = np.ptp(source_vertices, axis=0)
        up_axis = int(np.argmax(extents))
        horizontal = [axis for axis in range(3) if axis != up_axis]
        horizontal.sort(key=lambda axis: extents[axis], reverse=True)
        axis_order = [horizontal[0], up_axis, horizontal[1]]
        aligned_source = source_vertices[:, axis_order]
        if self.compare_mode:
            spacing = max(float(np.ptp(aligned_source[:, 0])) * 1.35, 0.65)
            offsets = np.linspace(-2.0, 2.0, 5) * spacing
            aligned = np.concatenate(
                [aligned_source + np.asarray((offset, 0.0, 0.0)) for offset in offsets], axis=0
            )
            faces = np.concatenate(
                [source_faces + index * len(aligned_source) for index in range(len(offsets))], axis=0
            )
        else:
            offsets = np.asarray((0.0,))
            aligned = aligned_source
            faces = source_faces

        skeleton_segments: list[tuple[np.ndarray, bool]] = []
        if self.show_skeleton:
            for bone in self.skeleton:
                head = np.asarray(bone.get("head", [0, 0, 0]), dtype=float)[axis_order]
                tail = np.asarray(bone.get("tail", [0, 0, 0]), dtype=float)[axis_order]
                name = str(bone.get("name", "")).lower()
                focused = not self.focus_patterns or any(pattern in name for pattern in self.focus_patterns)
                segment = np.stack((head, tail))
                for offset in offsets:
                    skeleton_segments.append((segment + np.asarray((offset, 0.0, 0.0)), focused))

        bounds = [aligned]
        if skeleton_segments:
            bounds.append(np.concatenate([segment for segment, _ in skeleton_segments], axis=0))
        all_points = np.concatenate(bounds, axis=0)
        center = (all_points.min(axis=0) + all_points.max(axis=0)) * 0.5
        cy, sy = np.cos(self.yaw), np.sin(self.yaw)
        cp, sp = np.cos(self.pitch), np.sin(self.pitch)
        yaw_matrix = np.asarray([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
        pitch_matrix = np.asarray([[1, 0, 0], [0, cp, -sp], [0, sp, cp]])
        rotation = pitch_matrix @ yaw_matrix
        rotated = (aligned - center) @ rotation.T
        rotated_skeleton = [((segment - center) @ rotation.T, focused) for segment, focused in skeleton_segments]
        span_points = np.concatenate([rotated] + [segment for segment, _ in rotated_skeleton], axis=0)
        span_x = max(float(np.ptp(span_points[:, 0])), 1e-9)
        span_y = max(float(np.ptp(span_points[:, 1])), 1e-9)
        scale = min(self.width() * 0.72 / span_x, self.height() * 0.74 / span_y) * self.zoom
        screen_center = np.asarray((self.width() / 2, self.height() * 0.56))
        projected = np.column_stack((rotated[:, 0] * scale, -rotated[:, 1] * scale)) + screen_center

        if len(faces) > 5200:
            face_indices = np.linspace(0, len(faces) - 1, 5200).astype(int)
            draw_faces = faces[face_indices]
        else:
            draw_faces = faces
        triangles = rotated[draw_faces]
        depth = triangles[:, :, 2].mean(axis=1)
        order = np.argsort(depth)
        normals = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
        lengths = np.linalg.norm(normals, axis=1)
        lengths[lengths == 0] = 1
        normals /= lengths[:, None]
        # Cool key, warm fill and cool rim, matching the installed kit's preview scenes.
        key = np.clip(normals @ np.asarray((-0.35, 0.48, 0.81)), 0, 1)
        fill = np.clip(normals @ np.asarray((0.70, -0.25, 0.30)), 0, 1)
        rim = np.clip(1.0 - np.abs(normals[:, 2]), 0, 1) ** 3
        vertex_weights = None
        if self.selected_bone and len(self.weights) == len(source_vertices):
            source_weight = np.asarray([float(row.get(self.selected_bone, 0.0)) for row in self.weights])
            vertex_weights = np.tile(source_weight, len(offsets))

        for draw_index in order:
            face = draw_faces[draw_index]
            polygon = QPolygonF([QPointF(float(projected[v, 0]), float(projected[v, 1])) for v in face])
            if vertex_weights is not None:
                weight = float(vertex_weights[face].mean())
                cold = np.asarray((32, 70, 125), dtype=float)
                hot = np.asarray((255, 174, 54), dtype=float)
                rgb = np.clip(cold * (1 - weight) + hot * weight, 0, 255).astype(int)
            else:
                base = np.asarray((66, 83, 104), dtype=float)
                rgb = np.clip(base * (0.42 + key[draw_index] * 0.70) + np.asarray((66, 32, 16)) * fill[draw_index] * 0.24 + np.asarray((45, 88, 130)) * rim[draw_index] * 0.30, 0, 255).astype(int)
            color = QColor(int(rgb[0]), int(rgb[1]), int(rgb[2]))
            painter.setBrush(color)
            painter.setPen(QPen(QColor(15, 20, 28, 150), 0.7) if self.wireframe else QPen(color, 0))
            painter.drawPolygon(polygon)

        if self.show_skeleton:
            for segment, focused in rotated_skeleton:
                points = [
                    QPointF(segment[i, 0] * scale + screen_center[0], -segment[i, 1] * scale + screen_center[1])
                    for i in range(2)
                ]
                painter.setPen(QPen(QColor("#ff6d4a") if focused else QColor("#637083"), 2.5 if focused else 1))
                painter.drawLine(points[0], points[1])
                painter.setBrush(QColor("#ffd36a") if focused else QColor("#7c8797"))
                painter.setPen(Qt.PenStyle.NoPen)
                radius = 2.7 if focused else 1.5
                painter.drawEllipse(points[0], radius, radius)

    def _draw_overlay(self, painter: QPainter) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(8, 12, 18, 215))
        painter.drawRoundedRect(QRectF(14, 14, 168, 29), 6, 6)
        painter.setPen(QColor("#7f8b9c"))
        font = painter.font()
        font.setPointSize(8)
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.drawText(QRectF(24, 14, 148, 29), Qt.AlignmentFlag.AlignVCenter, self.label)
        painter.setBrush(QColor(8, 12, 18, 215))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(QRectF(self.width() - 218, self.height() - 43, 204, 29), 6, 6)
        if self.weights:
            status = "PROVISIONAL AUTO-WEIGHTS" if self.weights_provisional else "REFERENCE WEIGHTS"
            color = QColor("#f1b65e") if self.weights_provisional else QColor("#64d4a0")
        elif self.skeleton:
            status, color = "SKELETON ALIGNMENT", QColor("#78b7fa")
        else:
            status, color = "MESH INSPECTION", QColor("#8996a8")
        painter.setPen(color)
        painter.drawText(QRectF(self.width() - 208, self.height() - 43, 184, 29), Qt.AlignmentFlag.AlignVCenter, status)


class AppSignals(QObject):
    log = Signal(str)
    preview_ready = Signal(object)
    preview_failed = Signal(str)
    skeleton_ready = Signal(object)
    skeleton_failed = Signal(str)
    finished = Signal(object)
    failed = Signal(str)


class ForgeStudio(QMainWindow):
    def __init__(self, load_official_skeleton: bool = True) -> None:
        super().__init__()
        self.setWindowTitle("Bannerlord Model Forge — Rigging Studio")
        self.resize(1520, 940)
        self.setMinimumSize(1180, 760)
        self.setAcceptDrops(True)
        self.source_path: Path | None = None
        self.source_asset: PreviewAsset | None = None
        self.preview_asset: PreviewAsset | None = None
        self.removed_parts: set[int] = set()
        self.active_rig_part_name = ""
        self.output_dir: Path | None = None
        self.skeleton_data_path: Path | None = None
        self.signals = AppSignals()
        self.signals.log.connect(self._log)
        self.signals.preview_ready.connect(self._show_source_preview)
        self.signals.preview_failed.connect(self._preview_failed)
        self.signals.skeleton_ready.connect(self._skeleton_ready)
        self.signals.skeleton_failed.connect(self._skeleton_failed)
        self.signals.finished.connect(self._pipeline_finished)
        self.signals.failed.connect(self._pipeline_failed)
        self.game = inspect_game_install()
        self.blender = detect_blender()
        self._build()
        self._log("Studio ready. Source and TaleWorlds files are always read-only.")
        if load_official_skeleton and self.game.human_skeleton_path and self.blender.found:
            self._log("Linking the official Bannerlord rest-pose skeleton…")
            threading.Thread(target=self._skeleton_worker, daemon=True).start()
        elif load_official_skeleton and self.game.human_skeleton_path:
            self.skeleton_status.setText("DETECTED • BLENDER REQUIRED")
            self.skeleton_detail.setText("Install or connect Blender to read the official FBX rest hierarchy.")

    def _build(self) -> None:
        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._top_bar())
        body = QSplitter(Qt.Orientation.Horizontal)
        body.setHandleWidth(1)
        body.addWidget(self._left_rail())
        body.addWidget(self._centre_workspace())
        body.addWidget(self._inspector())
        body.setSizes([270, 900, 340])
        body.setStretchFactor(0, 0)
        body.setStretchFactor(1, 1)
        body.setStretchFactor(2, 0)
        layout.addWidget(body, 1)

    def _top_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("TopBar")
        bar.setFixedHeight(58)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 0, 16, 0)
        logo = QLabel("MF")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setFixedSize(34, 34)
        logo.setStyleSheet("background:#398ceb;color:white;border-radius:7px;font-weight:800;font-size:12px;")
        title_stack = QVBoxLayout()
        title_stack.setSpacing(0)
        title = QLabel("Bannerlord Model Forge")
        title.setObjectName("Title")
        title_stack.addWidget(title)
        title_stack.addWidget(muted("BANNERLORD RIGGING WORKSPACE"))
        layout.addWidget(logo)
        layout.addLayout(title_stack)
        layout.addSpacing(20)
        project = QLabel("UNTITLED WORKSPACE")
        project.setObjectName("Accent")
        layout.addWidget(project)
        layout.addStretch(1)
        layout.addWidget(self._status_pill(f"Bannerlord {self.game.version or 'not found'}", bool(self.game.version)))
        layout.addWidget(self._status_pill("Modding Kit ready" if self.game.editor_found else "Modding Kit missing", self.game.editor_found))
        layout.addWidget(self._status_pill("Blender connected" if self.blender.found else "Blender missing", self.blender.found))
        return bar

    def _status_pill(self, text: str, good: bool) -> QFrame:
        pill = QFrame()
        pill.setObjectName("StatusGood" if good else "StatusWarn")
        row = QHBoxLayout(pill)
        row.setContentsMargins(10, 4, 10, 4)
        row.setSpacing(6)
        dot = QLabel("●")
        dot.setStyleSheet(f"color: {'#61d39d' if good else '#efb85f'}; font-size: 9px;")
        text_label = QLabel(text)
        text_label.setStyleSheet("font-size: 11px;")
        row.addWidget(dot)
        row.addWidget(text_label)
        return pill

    def _left_rail(self) -> QWidget:
        rail = QFrame()
        rail.setObjectName("LeftRail")
        rail.setMinimumWidth(250)
        rail.setMaximumWidth(310)
        layout = QVBoxLayout(rail)
        layout.setContentsMargins(14, 18, 14, 14)
        layout.setSpacing(12)
        layout.addWidget(section_label("Workspace"))
        self.drop_card = DropCard()
        self.drop_card.browse_requested.connect(self._browse_source)
        self.drop_card.file_selected.connect(self._set_source)
        layout.addWidget(self.drop_card)
        sample = QPushButton("Open generated fit-test mesh")
        sample.setObjectName("Quiet")
        sample.setToolTip("Generated test geometry only — this is not a Bannerlord body or skeleton.")
        sample.clicked.connect(self._load_sample)
        layout.addWidget(sample)
        layout.addSpacing(7)
        layout.addWidget(section_label("Scene outliner"))
        self.asset_list = QListWidget()
        self.asset_list.setMinimumHeight(112)
        self.asset_list.setMaximumHeight(260)
        self.asset_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.asset_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.asset_list.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.asset_list.itemSelectionChanged.connect(self._scene_selection_changed)
        self.asset_list.itemDoubleClicked.connect(lambda _item: self._frame_selected_part())
        placeholder = QListWidgetItem("Preparing linked Bannerlord rig…")
        placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
        self.asset_list.addItem(placeholder)
        layout.addWidget(self.asset_list)
        edit_row = QHBoxLayout()
        self.remove_part_button = QPushButton("Delete selected")
        self.remove_part_button.setObjectName("Quiet")
        self.remove_part_button.setEnabled(False)
        self.remove_part_button.setToolTip("Removes pieces only from this working scene. The original model is never changed.")
        self.remove_part_button.clicked.connect(self._remove_selected_parts)
        self.restore_parts_button = QPushButton("Restore all")
        self.restore_parts_button.setObjectName("Quiet")
        self.restore_parts_button.setEnabled(False)
        self.restore_parts_button.clicked.connect(self._restore_all_parts)
        edit_row.addWidget(self.remove_part_button, 1)
        edit_row.addWidget(self.restore_parts_button)
        layout.addLayout(edit_row)
        visibility_row = QHBoxLayout()
        self.solo_part_button = QPushButton("Solo selected")
        self.solo_part_button.setObjectName("Quiet")
        self.solo_part_button.setEnabled(False)
        self.solo_part_button.clicked.connect(self._solo_selected_part)
        self.show_set_button = QPushButton("Show set")
        self.show_set_button.setObjectName("Quiet")
        self.show_set_button.setEnabled(False)
        self.show_set_button.clicked.connect(self._show_working_set)
        visibility_row.addWidget(self.solo_part_button, 1)
        visibility_row.addWidget(self.show_set_button)
        layout.addLayout(visibility_row)
        self.return_to_set_button = QPushButton("← Return to imported set")
        self.return_to_set_button.setObjectName("Quiet")
        self.return_to_set_button.setVisible(False)
        self.return_to_set_button.clicked.connect(self._return_to_source_set)
        layout.addWidget(self.return_to_set_button)
        layout.addSpacing(7)
        layout.addWidget(section_label("Workflow"))
        self.workflow_labels: list[QLabel] = []
        for index, title in enumerate(("Import mesh", "Classify piece", "Optimize geometry", "Bind skeleton", "Validate poses", "Export package"), 1):
            row = QHBoxLayout()
            badge = QLabel(str(index))
            badge.setFixedSize(22, 22)
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge.setStyleSheet("background:#1e2734;color:#748297;border-radius:11px;font-size:10px;font-weight:700;")
            label = QLabel(title)
            label.setObjectName("Muted")
            self.workflow_labels.append(label)
            row.addWidget(badge)
            row.addWidget(label)
            row.addStretch(1)
            layout.addLayout(row)
        layout.addStretch(1)
        return rail

    def _centre_workspace(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        toolbar = QFrame()
        toolbar.setFixedHeight(48)
        toolbar.setStyleSheet("background:#121720;border-bottom:1px solid #252d3a;")
        row = QHBoxLayout(toolbar)
        row.setContentsMargins(12, 0, 12, 0)
        row.setSpacing(6)
        self.mode_single = QToolButton()
        self.mode_single.setText("Single fit")
        self.mode_single.setCheckable(True)
        self.mode_single.setChecked(True)
        self.mode_single.clicked.connect(self._select_single)
        self.mode_compare = QToolButton()
        self.mode_compare.setText("Compare")
        self.mode_compare.setCheckable(True)
        self.mode_compare.clicked.connect(self._toggle_compare)
        row.addWidget(self.mode_single)
        row.addWidget(self.mode_compare)
        row.addSpacing(12)
        for text, view in (("Front", (0.0, 0.0)), ("Side", (1.5708, 0.0)), ("3/4", (0.38, -0.10)), ("Top", (0.0, -1.30))):
            button = QToolButton()
            button.setText(text)
            button.clicked.connect(lambda _checked=False, angles=view: self.viewport.set_view(*angles))
            row.addWidget(button)
        row.addSpacing(8)
        self.frame_selection_button = QToolButton()
        self.frame_selection_button.setText("Focus")
        self.frame_selection_button.setEnabled(False)
        self.frame_selection_button.setToolTip("Zoom the camera to the selected armour piece. Double-clicking an outliner item does the same.")
        self.frame_selection_button.clicked.connect(self._frame_selected_part)
        row.addWidget(self.frame_selection_button)
        frame_all = QToolButton()
        frame_all.setText("Frame all")
        frame_all.clicked.connect(lambda: self.viewport.frame_all_parts())
        row.addWidget(frame_all)
        row.addStretch(1)
        self.vertex_chip = muted("VERTICES —")
        self.face_chip = muted("TRIANGLES —")
        self.bone_chip = muted("BONES —")
        row.addWidget(self.vertex_chip)
        row.addSpacing(12)
        row.addWidget(self.face_chip)
        row.addSpacing(12)
        row.addWidget(self.bone_chip)
        layout.addWidget(toolbar)

        middle = QSplitter(Qt.Orientation.Vertical)
        middle.setHandleWidth(1)
        self.viewport = RigViewport()
        self.viewport.bone_options_changed.connect(self._set_bones)
        self.viewport.statistics_changed.connect(self._set_statistics)
        self.viewport.render_error.connect(lambda message: self._log(f"GPU viewport error: {message}"))
        self.viewport.part_selected.connect(self._select_part_from_viewport)
        self.viewport.delete_requested.connect(self._remove_selected_parts)
        middle.addWidget(self.viewport)
        console_frame = QFrame()
        console_layout = QVBoxLayout(console_frame)
        console_layout.setContentsMargins(0, 0, 0, 0)
        console_layout.setSpacing(0)
        console_head = QFrame()
        console_head.setFixedHeight(34)
        console_head.setStyleSheet("background:#11161e;border-top:1px solid #242c38;border-bottom:1px solid #1b222d;")
        console_head_row = QHBoxLayout(console_head)
        console_head_row.setContentsMargins(12, 0, 12, 0)
        console_head_row.addWidget(section_label("Activity & validation"))
        console_head_row.addStretch(1)
        self.job_label = muted("IDLE")
        console_head_row.addWidget(self.job_label)
        self.console = QTextEdit()
        self.console.setObjectName("Console")
        self.console.setReadOnly(True)
        console_layout.addWidget(console_head)
        console_layout.addWidget(self.console)
        middle.addWidget(console_frame)
        middle.setSizes([690, 150])
        middle.setStretchFactor(0, 1)
        middle.setStretchFactor(1, 0)
        layout.addWidget(middle, 1)
        return container

    def _inspector(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("Inspector")
        panel.setMinimumWidth(310)
        panel.setMaximumWidth(390)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        self.inspector_tabs = QTabWidget()
        self.inspector_tabs.addTab(self._rig_tab(), "Rig setup")
        self.inspector_tabs.addTab(self._inspect_tab(), "Inspect")
        self.inspector_tabs.addTab(self._validate_tab(), "Validate")
        layout.addWidget(self.inspector_tabs, 1)
        action = QFrame()
        action.setStyleSheet("background:#10151d;border-top:1px solid #252d3a;")
        action_layout = QVBoxLayout(action)
        action_layout.setContentsMargins(14, 13, 14, 13)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.forge_button = QPushButton("Auto-rig selected piece")
        self.forge_button.setObjectName("Primary")
        self.forge_button.clicked.connect(self._start_pipeline)
        self.open_button = QPushButton("Open result folder")
        self.open_button.setEnabled(False)
        self.open_button.clicked.connect(self._open_output)
        action_layout.addWidget(self.progress)
        action_layout.addWidget(self.forge_button)
        action_layout.addWidget(self.open_button)
        layout.addWidget(action)
        return panel

    def _scroll_tab(self) -> tuple[QScrollArea, QVBoxLayout]:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(14, 16, 14, 18)
        content_layout.setSpacing(11)
        scroll.setWidget(content)
        return scroll, content_layout

    def _rig_tab(self) -> QWidget:
        scroll, layout = self._scroll_tab()
        layout.addWidget(section_label("Equipment slot"))
        self.piece_combo = QComboBox()
        for key, preset in PRESETS.items():
            self.piece_combo.addItem(preset.label, key)
        self.piece_combo.setCurrentIndex(list(PRESETS).index("body"))
        self.piece_combo.currentIndexChanged.connect(self._preset_changed)
        layout.addWidget(self.piece_combo)
        self.guidance = muted(PRESETS["body"].guidance, True)
        layout.addWidget(self.guidance)
        layout.addWidget(section_label("Geometry budget"))
        self.target_spin = QSpinBox()
        self.target_spin.setRange(4, 5_000_000)
        self.target_spin.setGroupSeparatorShown(True)
        self.target_spin.setValue(PRESETS["body"].triangle_target)
        self.target_spin.setSuffix(" triangles")
        layout.addWidget(self.target_spin)

        method_layout = QVBoxLayout()
        method_layout.setContentsMargins(12, 11, 12, 11)
        title = QLabel("Piece-aware automatic bind")
        title.setObjectName("Value")
        method_layout.addWidget(title)
        method_layout.addWidget(muted("Restricts candidate bones to this armour slot and caps each vertex at four normalized influences.", True))
        self.method_status = QLabel("PROVISIONAL — pose review required")
        self.method_status.setObjectName("Warning")
        method_layout.addWidget(self.method_status)
        self.auto_normalize_check = QCheckBox("Auto-fit untouched pieces before rigging")
        self.auto_normalize_check.setChecked(True)
        self.auto_normalize_check.setToolTip("If the selected piece still has its original transform, orient, scale, and place it on the chosen Bannerlord slot first.")
        method_layout.addWidget(self.auto_normalize_check)
        layout.addWidget(card(method_layout))

        layout.addWidget(section_label("Higher-confidence reference"))
        self.reference_edit = QLineEdit()
        self.reference_edit.setPlaceholderText("Optional weighted reference JSON")
        reference_row = QHBoxLayout()
        reference_row.addWidget(self.reference_edit, 1)
        reference_button = QPushButton("…")
        reference_button.setFixedWidth(36)
        reference_button.clicked.connect(self._browse_reference)
        reference_row.addWidget(reference_button)
        layout.addLayout(reference_row)

        skeleton_layout = QVBoxLayout()
        skeleton_layout.setContentsMargins(12, 11, 12, 11)
        skeleton_layout.addWidget(QLabel("Bannerlord human skeleton"))
        self.skeleton_status = QLabel("DETECTED • LOADING REST RIG" if self.game.human_skeleton_found else "NOT DETECTED")
        self.skeleton_status.setObjectName("Good" if self.game.human_skeleton_found else "Warning")
        skeleton_layout.addWidget(self.skeleton_status)
        self.skeleton_detail = muted("Loading exact bones from the installed TaleWorlds FBX. The source remains read-only.", True)
        skeleton_layout.addWidget(self.skeleton_detail)
        layout.addWidget(card(skeleton_layout))
        layout.addStretch(1)
        return scroll

    def _inspect_tab(self) -> QWidget:
        scroll, layout = self._scroll_tab()
        layout.addWidget(section_label("Selected piece orientation"))
        self.orientation_status = muted("Select one armour piece to rotate it.", True)
        layout.addWidget(self.orientation_status)
        self.placement_combo = QComboBox()
        self.placement_combo.addItem("Placement: auto", "auto")
        self.placement_combo.addItem("Placement: centre / pair", "centre")
        self.placement_combo.addItem("Placement: left side", "left")
        self.placement_combo.addItem("Placement: right side", "right")
        self.placement_combo.setToolTip("Choose left or right for a single pauldron, glove, bracer, boot, or greave.")
        self.auto_fit_button = QPushButton("Auto-fit to Bannerlord rig")
        self.auto_fit_button.setToolTip("Uses the selected slot, exact local rest rig, PCA orientation, uniform scale, and a reversible placement transform.")
        self.auto_fit_button.clicked.connect(self._auto_fit_selected_part)
        layout.addWidget(self.placement_combo)
        layout.addWidget(self.auto_fit_button)
        self.rotation_axis_combo = QComboBox()
        self.rotation_axis_combo.addItem("X axis", 0)
        self.rotation_axis_combo.addItem("Y axis", 1)
        self.rotation_axis_combo.addItem("Z axis", 2)
        self.rotation_axis_combo.setToolTip("Rotation uses the imported model's own axes and is preserved for Auto-rig/export.")
        self.rotate_minus_button = QPushButton("−90°")
        self.rotate_plus_button = QPushButton("+90°")
        self.rotate_minus_button.clicked.connect(lambda: self._rotate_selected_part(-90.0))
        self.rotate_plus_button.clicked.connect(lambda: self._rotate_selected_part(90.0))
        layout.addWidget(self.rotation_axis_combo)
        rotation_row = QHBoxLayout()
        self.rotate_180_button = QPushButton("Rotate 180°")
        self.rotate_180_button.setToolTip("Turns the selected piece over around the chosen axis.")
        self.rotate_180_button.clicked.connect(lambda: self._rotate_selected_part(180.0))
        self.reset_transform_button = QPushButton("Reset orientation")
        self.reset_transform_button.setObjectName("Quiet")
        self.reset_transform_button.clicked.connect(self._reset_selected_transform)
        rotation_row.addWidget(self.rotate_minus_button, 1)
        rotation_row.addWidget(self.rotate_plus_button, 1)
        rotation_row.addWidget(self.rotate_180_button, 1)
        layout.addLayout(rotation_row)
        layout.addWidget(self.reset_transform_button)
        self._set_transform_controls_enabled(False)
        layout.addSpacing(8)
        layout.addWidget(section_label("Material preview"))
        self.material_preview_combo = QComboBox()
        self.material_preview_combo.addItem("Studio lighting — approximate", "studio_lit")
        self.material_preview_combo.addItem("Base colour — exact source pixels", "base_color")
        self.material_preview_combo.setToolTip("Base colour shows the embedded image without viewport lighting. Studio lighting adds an approximate material preview.")
        self.material_preview_combo.currentIndexChanged.connect(self._material_preview_changed)
        layout.addWidget(self.material_preview_combo)
        self.material_source_status = muted(
            "Select one piece to inspect every material map actually supplied by its FBX.",
            True,
        )
        material_status_layout = QVBoxLayout()
        material_status_layout.setContentsMargins(11, 9, 11, 9)
        material_status_layout.addWidget(self.material_source_status)
        layout.addWidget(card(material_status_layout))
        self.texture_flip_u_check = QCheckBox("Flip texture horizontally (U)")
        self.texture_flip_v_check = QCheckBox("Flip texture vertically (V)")
        self.texture_flip_u_check.setToolTip("Corrects exporters that store the texture direction differently. Source UVs remain untouched.")
        self.texture_flip_v_check.setToolTip("Corrects exporters that store the texture direction differently. Source UVs remain untouched.")
        self.texture_flip_u_check.toggled.connect(self._texture_orientation_changed)
        self.texture_flip_v_check.toggled.connect(self._texture_orientation_changed)
        layout.addWidget(self.texture_flip_u_check)
        layout.addWidget(self.texture_flip_v_check)
        layout.addSpacing(8)
        layout.addWidget(section_label("Viewport overlays"))
        self.skeleton_check = QCheckBox("Show Bannerlord skeleton")
        self.skeleton_check.setChecked(True)
        self.skeleton_check.toggled.connect(self._set_skeleton_visible)
        self.wireframe_check = QCheckBox("Wireframe overlay")
        self.wireframe_check.toggled.connect(self._set_wireframe)
        layout.addWidget(self.skeleton_check)
        layout.addWidget(self.wireframe_check)
        layout.addSpacing(6)
        layout.addWidget(section_label("Weight heatmap"))
        self.bone_combo = QComboBox()
        self.bone_combo.addItem("Weight heatmap: off")
        self.bone_combo.setEnabled(False)
        self.bone_combo.currentTextChanged.connect(self.viewport_bone_changed)
        layout.addWidget(self.bone_combo)
        self.weight_status = muted("Run auto-rig or load a weighted reference to inspect influences.", True)
        layout.addWidget(self.weight_status)
        layout.addSpacing(8)
        layout.addWidget(section_label("Model statistics"))
        stats_layout = QVBoxLayout()
        stats_layout.setContentsMargins(12, 10, 12, 10)
        self.stats_rows: dict[str, QLabel] = {}
        for label_text in ("Vertices", "Triangles", "Skeleton bones", "Weight state"):
            row = QHBoxLayout()
            row.addWidget(muted(label_text))
            value = QLabel("—")
            value.setObjectName("Value")
            row.addStretch(1)
            row.addWidget(value)
            stats_layout.addLayout(row)
            self.stats_rows[label_text] = value
        layout.addWidget(card(stats_layout))
        layout.addStretch(1)
        return scroll

    def _validate_tab(self) -> QWidget:
        scroll, layout = self._scroll_tab()
        layout.addWidget(section_label("Game-ready gates"))
        self.validation_summary = muted("Run Auto-rig to replace this checklist with evidence from the selected piece.", True)
        layout.addWidget(self.validation_summary)
        self.validation_cards = QVBoxLayout()
        for title, detail in (
            ("Skeleton alignment", "Model must sit correctly on the Bannerlord bind pose."),
            ("Influence limits", "No more than four normalized weights per vertex."),
            ("Deformation poses", "Shoulders, waist, riding and crouch need visual review."),
            ("PBR material", "Convert roughness to glossiness and pack metallic/gloss/AO for pbr_metallic."),
            ("Clipping and cloth", "Inspect the equipped body, adjacent slots, collision capsules, and cloth anchors."),
            ("Modding Kit publish", "Resource Browser import, AssetPackages publish, and an in-game test are mandatory."),
        ):
            box_layout = QVBoxLayout()
            box_layout.setContentsMargins(11, 9, 11, 9)
            heading = QLabel("○  " + title)
            heading.setObjectName("Value")
            box_layout.addWidget(heading)
            box_layout.addWidget(muted(detail, True))
            widget = card(box_layout)
            self.validation_cards.addWidget(widget)
        layout.addLayout(self.validation_cards)
        layout.addStretch(1)
        return scroll

    def _browse_source(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import model", "", "3D models (*.fbx *.glb *.gltf *.obj *.ply *.stl);;All files (*.*)")
        if path:
            self._set_source(path)

    def _browse_reference(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose weighted reference", "", "Reference manifest (*.json)")
        if path:
            self.reference_edit.setText(path)

    def _load_sample(self) -> None:
        path = create_sample(project_root() / "work" / "samples" / "generated_fit_test.glb")
        self._set_source(str(path))
        self._log("Loaded generated fit-test geometry. It is not a Bannerlord body; the orange rig is the official local skeleton.")

    def _set_source(self, value: str) -> None:
        path = Path(value).expanduser().resolve()
        if not path.is_file():
            QMessageBox.warning(self, "Import failed", "That model file could not be found.")
            return
        if path.suffix.lower() not in {".fbx", ".glb", ".gltf", ".obj", ".ply", ".stl"}:
            QMessageBox.warning(self, "Unsupported format", "Choose FBX, GLB/GLTF, OBJ, PLY, or STL.")
            return
        self.source_path = path
        self.source_asset = None
        self.preview_asset = None
        self.removed_parts.clear()
        self.output_dir = None
        self.open_button.setEnabled(False)
        self.drop_card.set_path(path)
        self._refresh_scene_list()
        self.workflow_labels[0].setText("Import mesh  •  ready")
        self.workflow_labels[0].setStyleSheet("color:#6ed6a5;")
        self.job_label.setText("LOADING PREVIEW")
        self._log(f"Importing preview: {path.name}")
        threading.Thread(target=self._preview_worker, args=(path,), daemon=True).start()

    def _preview_worker(self, path: Path) -> None:
        try:
            if path.suffix.lower() == ".fbx":
                self.signals.log.emit("Converting FBX read-only through Blender for immediate viewport display…")
            asset = load_preview_asset(path, project_root() / "work" / "preview-cache")
            if path.suffix.lower() == ".fbx":
                self.signals.log.emit(f"FBX preview ready: {asset.display_path.name}")
            textured = 0
            texture_sizes: set[tuple[int, int]] = set()
            map_counts = {
                "base": 0,
                "normal": 0,
                "metal/rough": 0,
                "AO": 0,
                "emissive": 0,
            }
            for part in asset.parts:
                material = getattr(part.mesh.visual, "material", None)
                image = getattr(material, "baseColorTexture", None) if material is not None else None
                if image is None and material is not None:
                    image = getattr(material, "image", None)
                if image is not None and hasattr(image, "size"):
                    textured += 1
                    map_counts["base"] += 1
                    texture_sizes.add(tuple(int(value) for value in image.size))
                for label, attribute in (
                    ("normal", "normalTexture"),
                    ("metal/rough", "metallicRoughnessTexture"),
                    ("AO", "occlusionTexture"),
                    ("emissive", "emissiveTexture"),
                ):
                    candidate = getattr(material, attribute, None) if material is not None else None
                    if candidate is not None and hasattr(candidate, "size"):
                        map_counts[label] += 1
            texture_note = (
                " • textures " + ", ".join(f"{width}×{height}" for width, height in sorted(texture_sizes))
                if texture_sizes
                else " • no embedded base-colour image"
            )
            self.signals.log.emit(f"Detected {len(asset.parts)} selectable mesh pieces • {textured} UV-textured{texture_note}")
            self.signals.log.emit(
                "Material maps actually present across pieces • "
                + " • ".join(f"{label} {count}" for label, count in map_counts.items())
            )
            self.signals.preview_ready.emit(asset)
        except Exception as exc:
            self.signals.preview_failed.emit(f"Could not display {path.name}: {exc}")

    def _show_source_preview(self, payload: object) -> None:
        asset = payload  # type: ignore[assignment]
        if not isinstance(asset, PreviewAsset) or asset.source_path != self.source_path:
            return
        self.source_asset = asset
        self.preview_asset = asset
        self.removed_parts.clear()
        self.viewport.set_parts(
            asset.parts,
            self.skeleton_data_path,
            label=self.source_path.name,
            preset_key=self.piece_combo.currentData(),
        )
        materials = [getattr(part.mesh.visual, "material", None) for part in asset.parts]
        has_base_colour = any(
            getattr(material, "baseColorTexture", None) is not None
            or getattr(material, "image", None) is not None
            for material in materials
            if material is not None
        )
        has_pbr_support = any(
            any(
                getattr(material, attribute, None) is not None
                for attribute in ("normalTexture", "metallicRoughnessTexture", "occlusionTexture")
            )
            for material in materials
            if material is not None
        )
        if has_base_colour and not has_pbr_support:
            exact_index = self.material_preview_combo.findData("base_color")
            self.material_preview_combo.setCurrentIndex(exact_index)
            self._log(
                "This FBX supplies base colour only, so the viewport is showing exact source pixels by default. "
                "Studio lighting remains available as an approximation."
            )
        self.return_to_set_button.setVisible(False)
        self._refresh_scene_list()
        self.job_label.setText("READY TO ANALYZE")
        if len(asset.parts) > 1:
            self._log("Click a piece in the viewport or Scene outliner, then use Auto-rig selected piece. Delete removes only the working copy.")

    def _skeleton_worker(self) -> None:
        try:
            assert self.game.human_skeleton_path is not None
            data_path, bone_count = load_bannerlord_skeleton(
                Path(self.game.human_skeleton_path),
                project_root() / "work" / "skeleton-cache",
            )
            self.signals.skeleton_ready.emit((data_path, bone_count))
        except Exception as exc:
            self.signals.skeleton_failed.emit(str(exc))

    def _skeleton_ready(self, payload: object) -> None:
        data_path, bone_count = payload  # type: ignore[misc]
        self.skeleton_data_path = Path(data_path)
        self.viewport.set_skeleton_data(self.skeleton_data_path, self.piece_combo.currentData())
        self.skeleton_status.setText(f"LIVE • {bone_count} OFFICIAL BONES")
        self.skeleton_detail.setText("Exact rest hierarchy from the installed human_skeleton.fbx; referenced read-only.")
        self.bone_chip.setText(f"BONES  {bone_count:,}")
        self._refresh_scene_list()
        self._log(f"Official Bannerlord human_skeleton.fbx loaded • {bone_count} exact rest-pose bones.")

    def _skeleton_failed(self, message: str) -> None:
        self.skeleton_status.setText("RIG LOAD FAILED")
        self.skeleton_status.setObjectName("Warning")
        self.skeleton_status.style().unpolish(self.skeleton_status)
        self.skeleton_status.style().polish(self.skeleton_status)
        self.skeleton_detail.setText(message)
        self._log("Official skeleton unavailable: " + message)

    def _refresh_scene_list(self) -> None:
        self.asset_list.blockSignals(True)
        self.asset_list.clear()
        if self.preview_asset is not None:
            is_source = self.preview_asset is self.source_asset
            for index, part in enumerate(self.preview_asset.parts):
                if is_source and index in self.removed_parts:
                    continue
                material = getattr(part.mesh.visual, "material", None)
                image = getattr(material, "baseColorTexture", None) if material is not None else None
                if image is None and material is not None:
                    image = getattr(material, "image", None)
                texture_mark = "  ◉" if image is not None else ""
                item = QListWidgetItem(f"◇  {part.name}{texture_mark}")
                item.setData(Qt.ItemDataRole.UserRole, index)
                item.setToolTip(
                    f"{len(part.mesh.faces):,} triangles • {len(part.mesh.vertices):,} vertices"
                    + (" • UV texture" if image is not None else " • no texture image")
                )
                self.asset_list.addItem(item)
        if self.skeleton_data_path is not None:
            rig = QListWidgetItem("⟠  RIG  human_skeleton.fbx  [linked]")
            rig.setFlags(Qt.ItemFlag.NoItemFlags)
            self.asset_list.addItem(rig)
        if self.asset_list.count() == 0:
            placeholder = QListWidgetItem("Waiting for mesh and official rig…")
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self.asset_list.addItem(placeholder)
        self.asset_list.blockSignals(False)
        editable = self.preview_asset is not None and self.preview_asset is self.source_asset
        self.remove_part_button.setEnabled(False)
        self.restore_parts_button.setEnabled(editable and bool(self.removed_parts))
        self.solo_part_button.setEnabled(False)
        self.show_set_button.setEnabled(
            editable and any(index not in self.removed_parts for index in self.viewport.hidden_parts)
        )

    def _selected_part_indices(self) -> list[int]:
        values: list[int] = []
        for item in self.asset_list.selectedItems():
            value = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(value, int):
                values.append(value)
        return sorted(set(values))

    def _scene_selection_changed(self) -> None:
        indices = self._selected_part_indices()
        self.viewport.set_selected_part(indices[0] if len(indices) == 1 else -1)
        editable = self.preview_asset is not None and self.preview_asset is self.source_asset
        self.remove_part_button.setEnabled(editable and bool(indices))
        self.frame_selection_button.setEnabled(len(indices) == 1)
        self.solo_part_button.setEnabled(editable and len(indices) == 1)
        self._set_transform_controls_enabled(editable and len(indices) == 1)
        if len(indices) == 1 and self.preview_asset is not None:
            selected_part = self.preview_asset.parts[indices[0]]
            name = selected_part.name
            self.forge_button.setText(f"Auto-rig selected • {name[:22]}")
            if editable:
                self.inspector_tabs.setCurrentIndex(1)
            changed = not np.allclose(self.preview_asset.parts[indices[0]].transform, np.eye(4), rtol=0.0, atol=1e-12)
            self.orientation_status.setText(
                f"{name} • {'orientation modified' if changed else 'imported orientation'}"
            )
            inspection = inspect_source_material(selected_part.mesh)
            self.material_source_status.setText(material_inspection_text(inspection))
        else:
            self.forge_button.setText("Auto-rig selected piece")
            self.orientation_status.setText("Select one armour piece to rotate it.")
            self.material_source_status.setText(
                "Select one piece to inspect every material map actually supplied by its FBX."
            )

    def _set_transform_controls_enabled(self, enabled: bool) -> None:
        for control in (
            self.placement_combo,
            self.auto_fit_button,
            self.rotation_axis_combo,
            self.rotate_minus_button,
            self.rotate_plus_button,
            self.rotate_180_button,
            self.reset_transform_button,
        ):
            control.setEnabled(enabled)

    def _auto_fit_selected_part(self) -> bool:
        if (
            self.source_asset is None
            or self.preview_asset is not self.source_asset
            or self.skeleton_data_path is None
        ):
            QMessageBox.information(
                self,
                "Bannerlord rig not ready",
                "Wait for the official local Bannerlord skeleton to load, then select one piece.",
            )
            return False
        indices = self._selected_part_indices()
        if len(indices) != 1:
            return False
        index = indices[0]
        part = self.source_asset.parts[index]
        placement = str(self.placement_combo.currentData())
        if placement == "auto":
            lowered = part.name.lower()
            if re.search(r"(^|[_.\s-])(left|l)([_.\s-]|$)", lowered):
                placement = "left"
            elif re.search(r"(^|[_.\s-])(right|r)([_.\s-]|$)", lowered):
                placement = "right"
        try:
            result = auto_fit_to_bannerlord(
                part.mesh,
                self.skeleton_data_path,
                str(self.piece_combo.currentData()),
                placement,
            )
        except Exception as exc:
            QMessageBox.warning(self, "Auto-fit stopped", str(exc))
            return False
        part.transform = result.transform
        self.viewport.set_part_transform(index, part.transform)
        self.viewport.set_view(0.0, 0.0)
        self.viewport.frame_selected_part(index)
        self.orientation_status.setText(
            f"{part.name} • auto-fit {result.confidence:.0%} • scale ×{result.scale:.4g}"
        )
        self._log(
            f"Auto-fit {part.name} to {self.piece_combo.currentText()} ({result.placement}); "
            f"confidence {result.confidence:.0%}, uniform scale ×{result.scale:.4g}. {result.note}"
        )
        return True

    def _rotate_selected_part(self, degrees: float) -> None:
        if self.source_asset is None or self.preview_asset is not self.source_asset:
            return
        indices = self._selected_part_indices()
        if len(indices) != 1:
            return
        index = indices[0]
        part = self.source_asset.parts[index]
        axis = int(self.rotation_axis_combo.currentData())
        angle = np.deg2rad(degrees)
        cosine, sine = float(np.cos(angle)), float(np.sin(angle))
        rotation = np.eye(3, dtype=float)
        first, second = ((1, 2), (0, 2), (0, 1))[axis]
        rotation[first, first] = cosine
        rotation[second, second] = cosine
        rotation[first, second] = -sine if axis != 1 else sine
        rotation[second, first] = sine if axis != 1 else -sine
        center = np.asarray(part.mesh.bounds, dtype=float).mean(axis=0)
        delta = np.eye(4, dtype=float)
        delta[:3, :3] = rotation
        delta[:3, 3] = center - rotation @ center
        part.transform = delta @ np.asarray(part.transform, dtype=float)
        self.viewport.set_part_transform(index, part.transform)
        axis_name = "XYZ"[axis]
        self.orientation_status.setText(f"{part.name} • rotated {degrees:g}° around {axis_name}")
        self._log(f"Rotated {part.name} {degrees:g}° around its {axis_name} axis. Auto-rig/export will use this orientation.")

    def _reset_selected_transform(self) -> None:
        if self.source_asset is None or self.preview_asset is not self.source_asset:
            return
        indices = self._selected_part_indices()
        if len(indices) != 1:
            return
        index = indices[0]
        part = self.source_asset.parts[index]
        part.transform = np.eye(4, dtype=float)
        self.viewport.set_part_transform(index, part.transform)
        self.orientation_status.setText(f"{part.name} • imported orientation")
        self._log(f"Reset {part.name} to its imported orientation.")

    def _frame_selected_part(self) -> None:
        indices = self._selected_part_indices()
        if len(indices) == 1:
            self.viewport.frame_selected_part(indices[0])

    def _solo_selected_part(self) -> None:
        if self.preview_asset is None or self.preview_asset is not self.source_asset:
            return
        indices = self._selected_part_indices()
        if len(indices) != 1:
            return
        selected = indices[0]
        for index in range(len(self.preview_asset.parts)):
            self.viewport.set_part_visible(index, index == selected and index not in self.removed_parts)
        self.viewport.set_selected_part(selected)
        self.viewport.frame_selected_part(selected)
        self.show_set_button.setEnabled(True)

    def _show_working_set(self) -> None:
        if self.source_asset is None or self.preview_asset is not self.source_asset:
            return
        self.viewport.restore_all_parts()
        for index in self.removed_parts:
            self.viewport.set_part_visible(index, False)
        self.viewport.frame_all_parts()
        self.show_set_button.setEnabled(False)

    def _select_part_from_viewport(self, index: int) -> None:
        self.asset_list.clearSelection()
        for row in range(self.asset_list.count()):
            item = self.asset_list.item(row)
            if item.data(Qt.ItemDataRole.UserRole) == index:
                item.setSelected(True)
                self.asset_list.setCurrentItem(item)
                self.asset_list.scrollToItem(item)
                break

    def _remove_selected_parts(self) -> None:
        if self.preview_asset is None or self.preview_asset is not self.source_asset:
            return
        indices = self._selected_part_indices()
        if not indices and self.viewport.selected_part >= 0:
            indices = [self.viewport.selected_part]
        if not indices:
            return
        visible_count = len(self.preview_asset.parts) - len(self.removed_parts)
        if len(indices) >= visible_count:
            QMessageBox.information(self, "Keep one piece", "At least one mesh piece must remain in the working scene.")
            return
        names = [self.preview_asset.parts[index].name for index in indices]
        self.removed_parts.update(indices)
        for index in indices:
            self.viewport.set_part_visible(index, False)
        self.viewport.set_selected_part(-1)
        self._refresh_scene_list()
        self._log(f"Removed {len(indices)} working-scene piece(s): {', '.join(names[:3])}{'…' if len(names) > 3 else ''}. Original file untouched.")

    def _restore_all_parts(self) -> None:
        if self.source_asset is None:
            return
        restored = len(self.removed_parts)
        self.removed_parts.clear()
        self.preview_asset = self.source_asset
        self.viewport.restore_all_parts()
        self._refresh_scene_list()
        if restored:
            self._log(f"Restored {restored} piece(s) from the in-memory import. Original file was never modified.")

    def _return_to_source_set(self) -> None:
        if self.source_asset is None:
            return
        self.preview_asset = self.source_asset
        self.viewport.set_parts(
            self.source_asset.parts,
            self.skeleton_data_path,
            label=self.source_path.name if self.source_path else "Imported set",
            preset_key=self.piece_combo.currentData(),
        )
        for index in self.removed_parts:
            self.viewport.set_part_visible(index, False)
        self.return_to_set_button.setVisible(False)
        self._refresh_scene_list()
        self.job_label.setText("READY TO ANALYZE")

    def _preview_failed(self, message: str) -> None:
        self.job_label.setText("IMPORT FAILED")
        self._log("ERROR: " + message)
        QMessageBox.critical(self, "Model import failed", message)

    def _preset_changed(self) -> None:
        preset = PRESETS[self.piece_combo.currentData()]
        self.target_spin.setValue(preset.triangle_target)
        self.guidance.setText(preset.guidance)
        self.workflow_labels[1].setText(f"Classify piece  •  {preset.label}")
        self.workflow_labels[1].setStyleSheet("color:#6ed6a5;")
        if self.skeleton_data_path is not None:
            self.viewport.set_skeleton_data(self.skeleton_data_path, self.piece_combo.currentData())

    def _start_pipeline(self) -> None:
        if self.source_path is None or not self.source_path.is_file() or self.source_asset is None:
            QMessageBox.information(self, "Import a model", "Import an armour or weapon model first.")
            return
        if self.preview_asset is not self.source_asset:
            QMessageBox.information(self, "Return to imported set", "Return to the imported set before choosing another piece.")
            return
        indices = self._selected_part_indices()
        visible_indices = [
            index for index in range(len(self.source_asset.parts)) if index not in self.removed_parts
        ]
        if not indices and len(visible_indices) == 1:
            indices = visible_indices
        if len(indices) != 1:
            QMessageBox.information(
                self,
                "Select one piece",
                "Click exactly one armour piece in the 3D viewport or Scene outliner, then run Auto-rig selected piece.",
            )
            return
        selected_index = indices[0]
        if selected_index in self.removed_parts:
            QMessageBox.information(self, "Piece removed", "Restore that piece before auto-rigging it.")
            return
        selected_part = self.source_asset.parts[selected_index]
        if self.auto_normalize_check.isChecked() and np.allclose(
            selected_part.transform, np.eye(4), rtol=0.0, atol=1e-12
        ):
            if self.skeleton_data_path is None:
                QMessageBox.information(
                    self,
                    "Wait for the Bannerlord rig",
                    "Automatic normalization needs the official local rest rig. Wait for it to finish loading, or turn off automatic fit and place the piece manually.",
                )
                return
            if not self._auto_fit_selected_part():
                return
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", selected_part.name).strip("_.") or f"piece_{selected_index + 1:02d}"
        selected_source = project_root() / "work" / "selections" / f"{self.source_path.stem}-{safe_name}.glb"
        prepared_selection = selected_part.transformed_mesh()
        export_mesh(prepared_selection, selected_source)
        self.active_rig_part_name = selected_part.name
        reference = Path(self.reference_edit.text()).expanduser() if self.reference_edit.text().strip() else None
        self.forge_button.setEnabled(False)
        self.open_button.setEnabled(False)
        self.progress.setRange(0, 0)
        self.job_label.setText("ANALYZING & RIGGING")
        orientation_note = " • corrected orientation applied" if not np.allclose(selected_part.transform, np.eye(4), rtol=0.0, atol=1e-12) else ""
        self._log(f"Auto-rigging only: {selected_part.name} • {len(selected_part.mesh.faces):,} triangles{orientation_note}. Other set pieces are excluded.")
        for index in range(2, 5):
            self.workflow_labels[index].setStyleSheet("color:#62adff;")
        threading.Thread(
            target=self._pipeline_worker,
            args=(selected_source, self.piece_combo.currentData(), self.target_spin.value(), reference),
            daemon=True,
        ).start()

    def _pipeline_worker(self, source: Path, preset: str, target: int, reference: Path | None) -> None:
        try:
            result = run_pipeline(
                source,
                preset,
                target,
                reference_manifest=reference,
                progress=self.signals.log.emit,
            )
            mesh, _ = load_mesh(result.artifacts["prepared_glb"])
            self.signals.finished.emit((result, mesh))
        except Exception as exc:
            self.signals.failed.emit(str(exc))

    def _pipeline_finished(self, payload: object) -> None:
        result, mesh = payload  # type: ignore[misc]
        self.output_dir = result.output_dir
        result_name = f"{self.active_rig_part_name} • rig result" if self.active_rig_part_name else "Prepared rig result"
        result_part = MeshPart(result_name, mesh)
        self.preview_asset = PreviewAsset(self.source_path or result.artifacts["prepared_glb"], result.artifacts["prepared_glb"], [result_part])
        self.viewport.set_parts(
            [result_part],
            result.artifacts.get("skeleton_viewport_data", self.skeleton_data_path),
            result.artifacts.get("skin_weights"),
            result_name,
            result.preset_key,
        )
        self.return_to_set_button.setVisible(self.source_asset is not None and len(self.source_asset.parts) > 1)
        self._refresh_scene_list()
        self.forge_button.setEnabled(True)
        self.open_button.setEnabled(True)
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        errors = sum(item.level == "error" for item in result.validation)
        warnings = sum(item.level == "warning" for item in result.validation)
        self.job_label.setText("BLOCKED" if errors else "REVIEW REQUIRED")
        self.workflow_labels[2].setText("Optimize geometry  •  complete")
        self.workflow_labels[2].setStyleSheet("color:#6ed6a5;")
        if result.rigging.status == "weights_transferred":
            bind_state, bind_color = "reference weights", "#6ed6a5"
        elif result.rigging.status == "provisional_auto_weights":
            bind_state, bind_color = "provisional", "#f5bd68"
        elif result.rigging.status in {"rigid_asset_no_skinning", "rigid_weights_generated"}:
            bind_state, bind_color = "rigid item", "#6ed6a5"
        else:
            bind_state, bind_color = "blocked", "#ff7f86"
        self.workflow_labels[3].setText(f"Bind skeleton  •  {bind_state}")
        self.workflow_labels[3].setStyleSheet(f"color:{bind_color};")
        self.workflow_labels[4].setText("Validate poses  •  required")
        self.workflow_labels[4].setStyleSheet("color:#f5bd68;")
        has_fbx = any(
            key in result.artifacts
            for key in ("bannerlord_skinned_fbx", "bannerlord_provisional_skinned_fbx", "bannerlord_fbx")
        )
        self.workflow_labels[5].setText(
            "Export package  •  FBX staged" if has_fbx else "Export package  •  FBX missing"
        )
        self.workflow_labels[5].setStyleSheet("color:#f5bd68;")
        self._show_validation_results(result.validation)
        material_manifest = result.artifacts.get("material_manifest")
        if material_manifest and material_manifest.is_file():
            material_payload = json.loads(material_manifest.read_text(encoding="utf-8"))
            source_material = material_payload.get("source_material", {})
            source_slots = source_material.get("source_slots", {})
            detected = [
                label
                for key, label in (
                    ("albedo", "base colour"),
                    ("normal", "normal"),
                    ("metallic_roughness", "metal/rough"),
                    ("occlusion", "AO"),
                    ("emissive", "emissive"),
                )
                if source_slots.get(key, {}).get("present")
            ]
            generated = [Path(value).name for value in material_payload.get("outputs", {}).values()]
            self.material_source_status.setText(
                "Source maps: " + (", ".join(detected) if detected else "none")
                + "\nCompiled: " + (", ".join(generated) if generated else "none")
            )
        self._log(f"Prepared {result.before.triangles:,} → {result.after.triangles:,} triangles")
        self._log(f"Rigging: {result.rigging.status} • {result.rigging.confidence:.0%} confidence")
        self._log(f"Game-ready gates: {errors} errors • {warnings} warnings • Modding Kit import/publish still required")
        self._log(f"Output: {result.output_dir}")

    def _show_validation_results(self, validation: list) -> None:
        while self.validation_cards.count():
            item = self.validation_cards.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        counts = {
            level: sum(entry.level == level for entry in validation)
            for level in ("pass", "warning", "error", "info")
        }
        self.validation_summary.setText(
            f"{counts['pass']} passed  •  {counts['warning']} review  •  "
            f"{counts['error']} blocked  •  {counts['info']} informational"
        )
        icon_for = {"pass": "✓", "warning": "△", "error": "×", "info": "i"}
        object_for = {"pass": "Good", "warning": "Warning", "error": "Error", "info": "Accent"}
        for entry in validation:
            box_layout = QVBoxLayout()
            box_layout.setContentsMargins(11, 9, 11, 9)
            heading = QLabel(f"{icon_for.get(entry.level, '○')}  {entry.title}")
            heading.setObjectName(object_for.get(entry.level, "Value"))
            box_layout.addWidget(heading)
            box_layout.addWidget(muted(entry.detail, True))
            self.validation_cards.addWidget(card(box_layout))

    def _pipeline_failed(self, message: str) -> None:
        self.forge_button.setEnabled(True)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.job_label.setText("STOPPED")
        self._log("ERROR: " + message)
        QMessageBox.critical(self, "Forge stopped", message)

    def _set_bones(self, bones: list, provisional: bool) -> None:
        self.bone_combo.blockSignals(True)
        self.bone_combo.clear()
        self.bone_combo.addItem("Weight heatmap: off")
        self.bone_combo.addItems([str(name) for name in bones])
        self.bone_combo.setEnabled(bool(bones))
        self.bone_combo.blockSignals(False)
        if bones:
            self.weight_status.setText("Provisional automatic weights — inspect every major joint." if provisional else "Reference-transferred weights available for inspection.")
            self.weight_status.setObjectName("Warning" if provisional else "Good")
            self.weight_status.style().unpolish(self.weight_status)
            self.weight_status.style().polish(self.weight_status)
        else:
            self.weight_status.setText("Run auto-rig or load a weighted reference to inspect influences.")

    def _set_statistics(self, stats: dict) -> None:
        self.vertex_chip.setText(f"VERTICES  {stats['vertices']:,}")
        self.face_chip.setText(f"TRIANGLES  {stats['triangles']:,}")
        self.bone_chip.setText(f"BONES  {stats['bones']:,}")
        self.stats_rows["Vertices"].setText(f"{stats['vertices']:,}")
        self.stats_rows["Triangles"].setText(f"{stats['triangles']:,}")
        self.stats_rows["Skeleton bones"].setText(f"{stats['bones']:,}")
        self.stats_rows["Weight state"].setText("Available" if stats["weights"] else "Not generated")

    def viewport_bone_changed(self, text: str) -> None:
        self.viewport.set_selected_bone(text)

    def _set_skeleton_visible(self, checked: bool) -> None:
        self.viewport.show_skeleton = checked
        self.viewport.update()

    def _set_wireframe(self, checked: bool) -> None:
        self.viewport.wireframe = checked
        self.viewport.update()

    def _material_preview_changed(self) -> None:
        self.viewport.set_material_lit(self.material_preview_combo.currentData() == "studio_lit")

    def _texture_orientation_changed(self) -> None:
        self.viewport.set_uv_flip(self.texture_flip_u_check.isChecked(), self.texture_flip_v_check.isChecked())

    def _toggle_compare(self, checked: bool) -> None:
        self.mode_single.setChecked(not checked)
        self.viewport.compare_mode = checked
        self.viewport.update()
        self._log("Comparison stage selected: five synchronized fit/LOD slots." if checked else "Single fitting stage selected.")

    def _select_single(self) -> None:
        self.mode_single.setChecked(True)
        self.mode_compare.setChecked(False)
        self.viewport.compare_mode = False
        self.viewport.update()
        self._log("Single fitting stage selected.")

    def _open_output(self) -> None:
        if self.output_dir:
            os.startfile(self.output_dir)  # type: ignore[attr-defined]

    def _log(self, message: str) -> None:
        self.console.append(message)


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Bannerlord Model Forge")
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLE)
    window = ForgeStudio()
    window.show()
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()
