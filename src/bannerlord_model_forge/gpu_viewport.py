from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
from PySide6.QtCore import QPoint, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage, QKeyEvent, QMatrix4x4, QMouseEvent, QPainter, QPen, QSurfaceFormat, QVector3D, QVector4D, QWheelEvent
from PySide6.QtOpenGL import (
    QOpenGLBuffer,
    QOpenGLFunctions_3_3_Core,
    QOpenGLShader,
    QOpenGLShaderProgram,
    QOpenGLTexture,
    QOpenGLVertexArrayObject,
)
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import QSizePolicy

from .config import BONE_REGION_PATTERNS, PRESETS
from .mesh_io import MeshPart


GL_FLOAT = 0x1406
GL_TRIANGLES = 0x0004
GL_LINES = 0x0001
GL_POINTS = 0x0000
GL_DEPTH_TEST = 0x0B71
GL_MULTISAMPLE = 0x809D
GL_FRONT_AND_BACK = 0x0408
GL_LINE = 0x1B01
GL_FILL = 0x1B02
GL_COLOR_BUFFER_BIT = 0x00004000
GL_DEPTH_BUFFER_BIT = 0x00000100


VERTEX_SHADER = """#version 330 core
layout(location = 0) in vec3 a_position;
layout(location = 1) in vec3 a_normal;
layout(location = 2) in vec3 a_color;
layout(location = 3) in float a_weight;
layout(location = 4) in vec2 a_uv;

uniform mat4 u_model;
uniform mat4 u_view;
uniform mat4 u_projection;

out vec3 v_world;
out vec3 v_normal;
out vec3 v_color;
out float v_weight;
out vec2 v_uv;

void main() {
    vec4 world = u_model * vec4(a_position, 1.0);
    v_world = world.xyz;
    v_normal = normalize(mat3(transpose(inverse(u_model))) * a_normal);
    v_color = a_color;
    v_weight = a_weight;
    v_uv = a_uv;
    gl_Position = u_projection * u_view * world;
}
"""


FRAGMENT_SHADER = """#version 330 core
in vec3 v_world;
in vec3 v_normal;
in vec3 v_color;
in float v_weight;
in vec2 v_uv;

uniform int u_mode;
uniform int u_uv_flip;
uniform sampler2D u_base_texture;
uniform vec3 u_camera;

out vec4 fragColor;

vec3 linear_to_srgb(vec3 value) {
    return pow(clamp(value, 0.0, 1.0), vec3(1.0 / 2.2));
}

void main() {
    if (u_mode == 1) {
        vec3 floorColor = v_color;
        float radial = clamp(1.0 - length(v_world.xz) / 17.0, 0.24, 1.0);
        float frontFade = smoothstep(-7.0, 1.5, v_world.z);
        floorColor *= mix(0.72, 1.0, frontFade);
        fragColor = vec4(linear_to_srgb(floorColor * radial), 1.0);
        return;
    }
    if (u_mode == 2) {
        vec3 inactive = vec3(0.24, 0.30, 0.38);
        vec3 active = vec3(1.0, 0.27, 0.10);
        fragColor = vec4(mix(inactive, active, v_weight), 1.0);
        return;
    }

    vec3 N = normalize(v_normal);
    vec3 V = normalize(u_camera - v_world);
    vec3 keyDirection = normalize(vec3(-0.45, 0.72, 0.65));
    vec3 fillDirection = normalize(vec3(0.70, 0.18, 0.32));
    vec3 rimDirection = normalize(vec3(0.15, 0.40, -0.90));
    float key = max(dot(N, keyDirection), 0.0);
    float fill = max(dot(N, fillDirection), 0.0);
    float rim = pow(max(dot(N, rimDirection), 0.0), 2.0);
    vec3 halfVector = normalize(keyDirection + V);
    float specular = pow(max(dot(N, halfVector), 0.0), 34.0);

    bool textured = u_mode == 0 || u_mode == 4 || u_mode == 7 || u_mode == 8;
    bool selected = u_mode == 4 || u_mode == 5 || u_mode == 8;
    bool baseColorOnly = u_mode == 7 || u_mode == 8;
    bool heatmap = u_mode == 6;
    vec2 textureUv = v_uv;
    if (u_uv_flip == 1 || u_uv_flip == 3) textureUv.x = 1.0 - textureUv.x;
    if (u_uv_flip == 2 || u_uv_flip == 3) textureUv.y = 1.0 - textureUv.y;
    vec3 textureSample = textured ? texture(u_base_texture, textureUv).rgb : v_color;
    if (baseColorOnly) {
        vec3 exactColor = selected ? mix(textureSample, vec3(0.08, 0.52, 1.0), 0.04) : textureSample;
        fragColor = vec4(exactColor, 1.0);
        return;
    }
    vec3 base = textured ? pow(textureSample, vec3(2.2)) : v_color;
    if (heatmap) {
        vec3 cold = vec3(0.025, 0.12, 0.34);
        vec3 hot = vec3(1.0, 0.21, 0.025);
        vec3 peak = vec3(1.0, 0.88, 0.08);
        base = v_weight < 0.55
            ? mix(cold, hot, v_weight / 0.55)
            : mix(hot, peak, (v_weight - 0.55) / 0.45);
    }
    vec3 light = vec3(0.09) + vec3(0.46, 0.44, 0.41) * key + vec3(0.09, 0.10, 0.12) * fill;
    vec3 color = base * light + vec3(0.018, 0.022, 0.028) * rim + vec3(0.10) * specular;
    if (selected && !heatmap) {
        color *= 1.035;
    }
    fragColor = vec4(linear_to_srgb(color), 1.0);
}
"""


def _base_texture_image(mesh):
    material = getattr(mesh.visual, "material", None)
    if material is None:
        return None
    for field in ("baseColorTexture", "image"):
        value = getattr(material, field, None)
        if value is not None and hasattr(value, "convert") and hasattr(value, "size"):
            return value
    return None


def _neutral_vertex_colors(mesh, count: int) -> np.ndarray:
    fallback = np.tile(np.asarray((0.16, 0.205, 0.265), dtype=np.float32), (count, 1))
    if _base_texture_image(mesh) is not None and getattr(mesh.visual, "uv", None) is not None:
        return fallback
    try:
        colors = np.asarray(mesh.visual.to_color().vertex_colors[:, :3], dtype=np.float32) / 255.0
    except Exception:
        return fallback
    if len(colors) != count or not np.isfinite(colors).all():
        return fallback
    # Untextured imports are commonly solid white; a neutral gunmetal makes
    # surface curvature readable until the user assigns a material.
    if float(colors.mean()) > 0.94 and float(colors.std()) < 0.04:
        return fallback
    return np.clip(colors, 0.025, 1.0).astype(np.float32)


def _crease_aware_normals(vertices: np.ndarray, faces: np.ndarray) -> np.ndarray:
    """Smooth duplicate import vertices while retaining deliberate hard creases."""
    triangles = vertices[faces]
    face_normals = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    normals = np.zeros_like(vertices, dtype=np.float64)
    for corner in range(3):
        np.add.at(normals, faces[:, corner], face_normals)
    normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-12)

    # Blender/FBX commonly splits a smooth surface into duplicate vertices.
    # Rejoin normals only when their faces are within the smoothing angle, so a
    # cylinder remains round without turning its cap or armour plate edges soft.
    tolerance = max(float(np.ptp(vertices, axis=0).max()) * 1e-7, 1e-9)
    keys = np.rint(vertices / tolerance).astype(np.int64)
    _unique, inverse = np.unique(keys, axis=0, return_inverse=True)
    order = np.argsort(inverse, kind="stable")
    boundaries = np.flatnonzero(np.diff(inverse[order])) + 1
    cosine_limit = math.cos(math.radians(55.0))
    for group in np.split(order, boundaries):
        if len(group) < 2:
            continue
        cluster_sums: list[np.ndarray] = []
        cluster_members: list[list[int]] = []
        for index in group:
            normal = normals[index]
            selected = -1
            selected_dot = cosine_limit
            for cluster_index, cluster_sum in enumerate(cluster_sums):
                representative = cluster_sum / max(float(np.linalg.norm(cluster_sum)), 1e-12)
                similarity = float(np.dot(normal, representative))
                if similarity > selected_dot:
                    selected, selected_dot = cluster_index, similarity
            if selected < 0:
                cluster_sums.append(normal.copy())
                cluster_members.append([int(index)])
            else:
                cluster_sums[selected] += normal
                cluster_members[selected].append(int(index))
        for cluster_sum, members in zip(cluster_sums, cluster_members, strict=True):
            smoothed = cluster_sum / max(float(np.linalg.norm(cluster_sum)), 1e-12)
            normals[members] = smoothed
    return normals.astype(np.float32)


class RigViewport(QOpenGLWidget):
    """Depth-buffered GPU viewport for mesh, skeleton, and weight inspection."""

    bone_options_changed = Signal(list, bool)
    statistics_changed = Signal(dict)
    render_error = Signal(str)
    part_selected = Signal(int)
    delete_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        fmt = QSurfaceFormat()
        fmt.setRenderableType(QSurfaceFormat.RenderableType.OpenGL)
        fmt.setVersion(3, 3)
        fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
        fmt.setDepthBufferSize(24)
        fmt.setStencilBufferSize(8)
        fmt.setSamples(4)
        fmt.setSwapBehavior(QSurfaceFormat.SwapBehavior.DoubleBuffer)
        self.setFormat(fmt)
        self.setMinimumSize(560, 430)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.OpenHandCursor)

        self.mesh = None
        self.parts: list[MeshPart] = []
        self.hidden_parts: set[int] = set()
        self.selected_part = -1
        self.framed_part = -1
        self.skeleton: list[dict[str, object]] = []
        self.weights: list[dict[str, float]] = []
        self.weights_provisional = False
        self.focus_patterns: tuple[str, ...] = ()
        self.selected_bone = ""
        self.wireframe = False
        self.show_skeleton = True
        self.material_lit = True
        self.uv_flip_bits = 0
        self.compare_mode = False
        self.yaw = math.radians(22.0)
        self.pitch = math.radians(7.0)
        self.zoom = 1.0
        self.last_mouse: QPoint | None = None
        self._press_mouse: QPoint | None = None
        self._mouse_dragged = False
        self.label = "FITTING STAGE"

        self._gl: QOpenGLFunctions_3_3_Core | None = None
        self._program: QOpenGLShaderProgram | None = None
        self._model_vao: QOpenGLVertexArrayObject | None = None
        self._model_vbo: QOpenGLBuffer | None = None
        self._floor_vao: QOpenGLVertexArrayObject | None = None
        self._floor_vbo: QOpenGLBuffer | None = None
        self._skeleton_vao: QOpenGLVertexArrayObject | None = None
        self._skeleton_vbo: QOpenGLBuffer | None = None
        self._gpu_ready = False
        self._index_count = 0
        self._skeleton_vertex_count = 0
        self._floor_vertex_count = 0
        self._mesh_interleaved = np.empty((0, 12), dtype=np.float32)
        self._skeleton_interleaved = np.empty((0, 12), dtype=np.float32)
        self._part_ranges: list[tuple[int, int, int]] = []
        self._part_bounds: dict[int, tuple[np.ndarray, np.ndarray]] = {}
        self._part_base_bounds: dict[int, tuple[np.ndarray, np.ndarray]] = {}
        self._part_texture_slots: dict[int, int] = {}
        self._texture_images: dict[int, QImage] = {}
        self._gl_textures: dict[int, QOpenGLTexture] = {}
        self._model_height = 2.0
        self._model_width = 0.8
        self._floor_height = 0.0
        self._normalization_scale = 1.0
        self._normalization_origin = np.zeros(3, dtype=float)
        self._axis_order = [0, 2, 1]
        self._source_to_normalized = np.eye(4, dtype=float)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(900, 650)

    def set_model(
        self,
        mesh,
        skeleton_path: Path | None = None,
        weights_path: Path | None = None,
        label: str = "Imported model",
        preset_key: str | None = None,
    ) -> None:
        self.set_parts(
            [MeshPart(label, mesh)],
            skeleton_path=skeleton_path,
            weights_path=weights_path,
            label=label,
            preset_key=preset_key,
        )

    def set_parts(
        self,
        parts: list[MeshPart],
        skeleton_path: Path | None = None,
        weights_path: Path | None = None,
        label: str = "Imported model",
        preset_key: str | None = None,
    ) -> None:
        self.parts = list(parts)
        self.mesh = self.parts[0].mesh if self.parts else None
        self.hidden_parts.clear()
        self.selected_part = -1
        self.framed_part = -1
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
        self._prepare_cpu_geometry()
        self._upload_if_ready()
        self.bone_options_changed.emit(bones, self.weights_provisional)
        self.statistics_changed.emit(
            {
                "vertices": sum(len(part.mesh.vertices) for part in self.parts),
                "triangles": sum(len(part.mesh.faces) for part in self.parts),
                "bones": len(self.skeleton),
                "weights": bool(bones),
            }
        )
        self.set_view(math.radians(22.0), math.radians(7.0))

    def set_selected_part(self, index: int) -> None:
        self.selected_part = index if 0 <= index < len(self.parts) and index not in self.hidden_parts else -1
        self.update()

    def set_material_lit(self, lit: bool) -> None:
        """Switch between exact base-colour inspection and studio lighting."""
        self.material_lit = bool(lit)
        self.update()

    def set_uv_flip(self, flip_u: bool, flip_v: bool) -> None:
        """Correct texture-coordinate orientation without touching source UVs."""
        self.uv_flip_bits = (1 if flip_u else 0) | (2 if flip_v else 0)
        self.update()

    def set_part_transform(self, index: int, matrix: np.ndarray) -> None:
        """Apply a fast, non-destructive source-space transform to one piece."""
        if not 0 <= index < len(self.parts):
            return
        self.parts[index].transform = np.asarray(matrix, dtype=float).reshape((4, 4)).copy()
        self._refresh_part_bounds(index)
        self.update()

    def frame_selected_part(self, index: int | None = None) -> None:
        target = self.selected_part if index is None else index
        if target in self._part_bounds and target not in self.hidden_parts:
            self.framed_part = target
            self.zoom = 1.0
            self.update()

    def frame_all_parts(self) -> None:
        self.framed_part = -1
        self.zoom = 1.0
        self.update()

    def set_part_visible(self, index: int, visible: bool) -> None:
        if not 0 <= index < len(self.parts):
            return
        if visible:
            self.hidden_parts.discard(index)
        else:
            self.hidden_parts.add(index)
            if self.selected_part == index:
                self.selected_part = -1
            if self.framed_part == index:
                self.framed_part = -1
        self._emit_visible_statistics()
        self.update()

    def restore_all_parts(self) -> None:
        self.hidden_parts.clear()
        self._emit_visible_statistics()
        self.update()

    def _emit_visible_statistics(self) -> None:
        visible = [part for index, part in enumerate(self.parts) if index not in self.hidden_parts]
        self.statistics_changed.emit(
            {
                "vertices": sum(len(part.mesh.vertices) for part in visible),
                "triangles": sum(len(part.mesh.faces) for part in visible),
                "bones": len(self.skeleton),
                "weights": bool(self.weights),
            }
        )

    def set_skeleton_data(self, skeleton_path: Path, preset_key: str | None = None) -> None:
        """Display an extracted rest rig independently of mesh processing."""
        payload = json.loads(skeleton_path.read_text(encoding="utf-8"))
        self.skeleton = list(payload.get("bones", []))
        if self.mesh is None:
            self.label = "OFFICIAL BANNERLORD REST RIG • LINKED"
        self.focus_patterns = (
            BONE_REGION_PATTERNS.get(PRESETS[preset_key].skeleton_region, ())
            if preset_key in PRESETS
            else ()
        )
        self._prepare_cpu_geometry()
        self._upload_if_ready()
        self.statistics_changed.emit(
            {
                "vertices": sum(len(part.mesh.vertices) for index, part in enumerate(self.parts) if index not in self.hidden_parts),
                "triangles": sum(len(part.mesh.faces) for index, part in enumerate(self.parts) if index not in self.hidden_parts),
                "bones": len(self.skeleton),
                "weights": bool(self.weights),
            }
        )
        self.update()

    def clear(self) -> None:
        self.mesh = None
        self.parts = []
        self.hidden_parts.clear()
        self.selected_part = -1
        self.framed_part = -1
        self.skeleton = []
        self.weights = []
        self._mesh_interleaved = np.empty((0, 12), dtype=np.float32)
        self._skeleton_interleaved = np.empty((0, 12), dtype=np.float32)
        self._part_ranges = []
        self._part_bounds = {}
        self._part_base_bounds = {}
        self._part_texture_slots = {}
        self._texture_images = {}
        self._upload_if_ready()
        self.update()

    def set_view(self, yaw: float, pitch: float) -> None:
        self.yaw, self.pitch, self.zoom = yaw, pitch, 1.0
        self.update()

    def set_selected_bone(self, name: str) -> None:
        self.selected_bone = "" if name.startswith("Weight heatmap") else name
        if self.mesh is not None:
            self._prepare_cpu_geometry()
            self._upload_if_ready()
        self.update()

    def initializeGL(self) -> None:  # noqa: N802
        try:
            self._gl = QOpenGLFunctions_3_3_Core()
            if not self._gl.initializeOpenGLFunctions():
                raise RuntimeError("OpenGL 3.3 functions could not be initialized.")
            self._program = QOpenGLShaderProgram(self)
            if not self._program.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Vertex, VERTEX_SHADER):
                raise RuntimeError(self._program.log())
            if not self._program.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Fragment, FRAGMENT_SHADER):
                raise RuntimeError(self._program.log())
            if not self._program.link():
                raise RuntimeError(self._program.log())
            self._model_vao = QOpenGLVertexArrayObject(self)
            self._model_vbo = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
            self._floor_vao = QOpenGLVertexArrayObject(self)
            self._floor_vbo = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
            self._skeleton_vao = QOpenGLVertexArrayObject(self)
            self._skeleton_vbo = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
            self._create_floor_geometry()
            self._gpu_ready = True
            self._upload_model_geometry()
            self._gl.glEnable(GL_DEPTH_TEST)
            self._gl.glEnable(GL_MULTISAMPLE)
            self._gl.glClearColor(0.035, 0.052, 0.075, 1.0)
        except Exception as exc:
            self._gpu_ready = False
            self.render_error.emit(str(exc))

    def resizeGL(self, width: int, height: int) -> None:  # noqa: N802
        if self._gl is not None:
            self._gl.glViewport(0, 0, max(1, width), max(1, height))

    def paintGL(self) -> None:  # noqa: N802
        if self._gl is None:
            return
        self._gl.glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        if self._gpu_ready and self._program is not None:
            projection, view, camera = self._camera_matrices()
            self._program.bind()
            self._program.setUniformValue("u_projection", projection)
            self._program.setUniformValue("u_view", view)
            self._program.setUniformValue("u_camera", camera)
            self._draw_floor()
            if self._index_count:
                self._draw_models()
            if self.show_skeleton and self._skeleton_vertex_count:
                self._draw_skeletons()
            self._program.release()
        self._draw_qt_overlay()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self.last_mouse = event.position().toPoint()
            self._press_mouse = self.last_mouse
            self._mouse_dragged = False
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton and not self._mouse_dragged:
            selected = self._pick_part(event.position().x(), event.position().y())
            if selected >= 0:
                self.set_selected_part(selected)
                self.part_selected.emit(selected)
        self.last_mouse = None
        self._press_mouse = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if self.last_mouse is None:
            return
        point = event.position().toPoint()
        delta = point - self.last_mouse
        if self._press_mouse is not None and (point - self._press_mouse).manhattanLength() > 4:
            self._mouse_dragged = True
        self.last_mouse = point
        self.yaw -= delta.x() * 0.009
        self.pitch = float(np.clip(self.pitch + delta.y() * 0.009, math.radians(-75), math.radians(75)))
        self.update()

    def wheelEvent(self, event: QWheelEvent) -> None:  # type: ignore[override]
        self.zoom = float(np.clip(self.zoom * (1.12 if event.angleDelta().y() > 0 else 0.89), 0.35, 4.5))
        self.update()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # type: ignore[override]
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.delete_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def _prepare_cpu_geometry(self) -> None:
        if not self.parts and not self.skeleton:
            return
        skeleton_points = np.asarray(
            [bone.get("head", (0.0, 0.0, 0.0)) for bone in self.skeleton],
            dtype=np.float64,
        )
        model_points = [np.asarray(part.mesh.vertices, dtype=np.float64) for part in self.parts if len(part.mesh.vertices)]
        model_reference = np.vstack(model_points) if model_points else np.empty((0, 3), dtype=np.float64)
        axis_reference = skeleton_points if len(skeleton_points) else model_reference
        extents = np.ptp(axis_reference, axis=0)
        up_axis = int(np.argmax(extents))
        horizontal = [axis for axis in range(3) if axis != up_axis]
        horizontal.sort(key=lambda axis: extents[axis], reverse=True)
        self._axis_order = [horizontal[0], up_axis, horizontal[1]]
        aligned_reference = axis_reference[:, self._axis_order]
        minimum = aligned_reference.min(axis=0)
        maximum = aligned_reference.max(axis=0)
        self._normalization_origin = np.asarray(((minimum[0] + maximum[0]) * 0.5, minimum[1], (minimum[2] + maximum[2]) * 0.5))
        height = max(float(maximum[1] - minimum[1]), 1e-6)
        self._normalization_scale = 2.0 / height
        basis = np.zeros((3, 3), dtype=float)
        for target_axis, source_axis in enumerate(self._axis_order):
            basis[target_axis, source_axis] = self._normalization_scale
        self._source_to_normalized = np.eye(4, dtype=float)
        self._source_to_normalized[:3, :3] = basis
        self._source_to_normalized[:3, 3] = -self._normalization_origin * self._normalization_scale
        framing_reference = np.vstack([value for value in (model_reference, skeleton_points) if len(value)])
        normalized_reference = (framing_reference[:, self._axis_order] - self._normalization_origin) * self._normalization_scale
        self._model_height = max(float(np.ptp(normalized_reference[:, 1])), 0.25)
        self._model_width = max(float(np.ptp(normalized_reference[:, 0])), 0.25)
        self._floor_height = float(normalized_reference[:, 1].min())

        mesh_rows: list[np.ndarray] = []
        self._part_ranges = []
        self._part_bounds = {}
        self._part_base_bounds = {}
        self._part_texture_slots = {}
        self._texture_images = {}
        texture_keys: dict[tuple[object, ...], int] = {}
        cursor = 0
        for part_index, part in enumerate(self.parts):
            mesh = part.mesh
            if not len(mesh.faces):
                continue
            vertices = np.asarray(mesh.vertices, dtype=np.float64)
            faces = np.asarray(mesh.faces, dtype=np.uint32)
            aligned = vertices[:, self._axis_order]
            positions = ((aligned - self._normalization_origin) * self._normalization_scale).astype(np.float32)
            # GLB previews carry Blender's authored split/smoothed normals.
            # Prefer those exactly; recomputing them makes hard-surface armour
            # look faceted and can turn a clean material into triangular noise.
            cached = getattr(getattr(mesh, "_cache", None), "cache", {}).get("vertex_normals")
            source_normals = (
                np.asarray(cached, dtype=np.float64)
                if cached is not None
                else np.empty((0, 3), dtype=np.float64)
            )
            if len(source_normals) != len(vertices) or not np.isfinite(source_normals).all():
                source_normals = _crease_aware_normals(vertices, np.asarray(mesh.faces, dtype=int))
            normals = source_normals[:, self._axis_order]
            colors = _neutral_vertex_colors(mesh, len(vertices))
            weights = np.zeros((len(vertices), 1), dtype=np.float32)
            if len(self.parts) == 1 and self.selected_bone and len(self.weights) == len(vertices):
                weights[:, 0] = np.asarray([float(row.get(self.selected_bone, 0.0)) for row in self.weights], dtype=np.float32)
            source_uv = getattr(mesh.visual, "uv", None)
            uv = (
                np.asarray(source_uv, dtype=np.float32)[:, :2]
                if source_uv is not None and len(source_uv) == len(vertices)
                else np.zeros((len(vertices), 2), dtype=np.float32)
            )
            per_vertex = np.column_stack((positions, normals, colors, weights, uv)).astype(np.float32)
            expanded = per_vertex[faces.reshape(-1)].copy()
            mesh_rows.append(expanded)
            count = len(expanded)
            self._part_ranges.append((part_index, cursor, count))
            cursor += count
            bounds = (positions.min(axis=0), positions.max(axis=0))
            self._part_base_bounds[part_index] = bounds
            self._part_bounds[part_index] = bounds

            image = _base_texture_image(mesh)
            if image is not None and source_uv is not None:
                material = getattr(mesh.visual, "material", None)
                key = (
                    str(getattr(material, "name", "")),
                    tuple(getattr(image, "size", ())),
                    str(getattr(image, "filename", "")),
                )
                slot = texture_keys.get(key)
                if slot is None:
                    slot = len(texture_keys)
                    texture_keys[key] = slot
                    rgba = image.convert("RGBA")
                    raw = rgba.tobytes("raw", "RGBA")
                    self._texture_images[slot] = QImage(
                        raw,
                        int(rgba.size[0]),
                        int(rgba.size[1]),
                        QImage.Format.Format_RGBA8888,
                    ).copy()
                self._part_texture_slots[part_index] = slot
        self._mesh_interleaved = np.vstack(mesh_rows) if mesh_rows else np.empty((0, 12), dtype=np.float32)
        for part_index in self._part_base_bounds:
            self._refresh_part_bounds(part_index)

        skeleton_rows: list[np.ndarray] = []
        heads = {str(bone.get("name", "")): np.asarray(bone.get("head", [0.0, 0.0, 0.0]), dtype=float) for bone in self.skeleton}
        for bone in self.skeleton:
            name = str(bone.get("name", "")).lower()
            focused = not self.focus_patterns or any(pattern in name for pattern in self.focus_patterns)
            parent = heads.get(str(bone.get("parent", "")))
            endpoints = (
                (parent, np.asarray(bone.get("head", [0.0, 0.0, 0.0]), dtype=float))
                if parent is not None
                else (
                    np.asarray(bone.get("head", [0.0, 0.0, 0.0]), dtype=float),
                    np.asarray(bone.get("tail", [0.0, 0.0, 0.0]), dtype=float),
                )
            )
            for point_value in endpoints:
                point = point_value[self._axis_order]
                position = (point - self._normalization_origin) * self._normalization_scale
                skeleton_rows.append(
                    np.asarray((*position, 0.0, 1.0, 0.0, 1.0, 0.27, 0.10, 1.0 if focused else 0.0, 0.0, 0.0), dtype=np.float32)
                )
        self._skeleton_interleaved = np.vstack(skeleton_rows) if skeleton_rows else np.empty((0, 12), dtype=np.float32)

    def _upload_if_ready(self) -> None:
        if not self._gpu_ready or not self.isValid():
            self.update()
            return
        self.makeCurrent()
        try:
            self._upload_model_geometry()
        finally:
            self.doneCurrent()
        self.update()

    def _upload_model_geometry(self) -> None:
        if self._program is None or self._model_vao is None or self._model_vbo is None:
            return
        if not self._model_vao.isCreated():
            self._model_vao.create()
        if not self._model_vbo.isCreated():
            self._model_vbo.create()
        self._program.bind()
        self._model_vao.bind()
        self._model_vbo.bind()
        self._model_vbo.allocate(self._mesh_interleaved.tobytes(), self._mesh_interleaved.nbytes)
        stride = 12 * 4
        for location, offset, size in ((0, 0, 3), (1, 3 * 4, 3), (2, 6 * 4, 3), (3, 9 * 4, 1), (4, 10 * 4, 2)):
            self._program.enableAttributeArray(location)
            self._program.setAttributeBuffer(location, GL_FLOAT, offset, size, stride)
        self._model_vao.release()
        self._model_vbo.release()
        self._index_count = len(self._mesh_interleaved)
        for texture in self._gl_textures.values():
            if texture.isCreated():
                texture.destroy()
        self._gl_textures = {}
        for slot, image in self._texture_images.items():
            # QImage rows start at the top; OpenGL UVs start at the bottom.
            texture = QOpenGLTexture(image.mirrored(False, True))
            # Some Windows drivers expose incomplete auto-generated mip levels
            # for large embedded FBX atlases, producing triangle-shaped blotches.
            # Linear sampling from the verified source image is stable and exact.
            texture.setMinificationFilter(QOpenGLTexture.Filter.Linear)
            texture.setMagnificationFilter(QOpenGLTexture.Filter.Linear)
            texture.setWrapMode(QOpenGLTexture.WrapMode.Repeat)
            self._gl_textures[slot] = texture

        assert self._skeleton_vao is not None and self._skeleton_vbo is not None
        if not self._skeleton_vao.isCreated():
            self._skeleton_vao.create()
        if not self._skeleton_vbo.isCreated():
            self._skeleton_vbo.create()
        self._skeleton_vao.bind()
        self._skeleton_vbo.bind()
        self._skeleton_vbo.allocate(self._skeleton_interleaved.tobytes(), self._skeleton_interleaved.nbytes)
        for location, offset, size in ((0, 0, 3), (1, 3 * 4, 3), (2, 6 * 4, 3), (3, 9 * 4, 1), (4, 10 * 4, 2)):
            self._program.enableAttributeArray(location)
            self._program.setAttributeBuffer(location, GL_FLOAT, offset, size, stride)
        self._skeleton_vao.release()
        self._skeleton_vbo.release()
        self._skeleton_vertex_count = len(self._skeleton_interleaved)
        self._program.release()

    def _create_floor_geometry(self) -> None:
        assert self._program is not None and self._floor_vao is not None and self._floor_vbo is not None
        positions: list[tuple[float, float, float]] = []
        colors_list: list[tuple[float, float, float]] = []
        tile_size = 0.5
        tile_count = 72
        start = -tile_count * tile_size * 0.5
        dark = (0.014, 0.020, 0.029)
        light = (0.050, 0.061, 0.077)
        for row in range(tile_count):
            z0, z1 = start + row * tile_size, start + (row + 1) * tile_size
            for column in range(tile_count):
                x0, x1 = start + column * tile_size, start + (column + 1) * tile_size
                positions.extend(((x0, 0.0, z0), (x1, 0.0, z0), (x1, 0.0, z1),
                                  (x0, 0.0, z0), (x1, 0.0, z1), (x0, 0.0, z1)))
                colors_list.extend([light if (row + column) % 2 else dark] * 6)
        floor = np.asarray(positions, dtype=np.float32)
        normals = np.tile(np.asarray((0.0, 1.0, 0.0), dtype=np.float32), (len(floor), 1))
        colors = np.asarray(colors_list, dtype=np.float32)
        weights = np.zeros((len(floor), 1), dtype=np.float32)
        uv = np.zeros((len(floor), 2), dtype=np.float32)
        data = np.column_stack((floor, normals, colors, weights, uv)).astype(np.float32)
        self._floor_vao.create()
        self._floor_vbo.create()
        self._program.bind()
        self._floor_vao.bind()
        self._floor_vbo.bind()
        self._floor_vbo.allocate(data.tobytes(), data.nbytes)
        self._floor_vertex_count = len(data)
        stride = 12 * 4
        for location, offset, size in ((0, 0, 3), (1, 3 * 4, 3), (2, 6 * 4, 3), (3, 9 * 4, 1), (4, 10 * 4, 2)):
            self._program.enableAttributeArray(location)
            self._program.setAttributeBuffer(location, GL_FLOAT, offset, size, stride)
        self._floor_vao.release()
        self._floor_vbo.release()
        self._program.release()

    def _camera_matrices(self) -> tuple[QMatrix4x4, QMatrix4x4, QVector3D]:
        if self.framed_part in self._part_bounds and not self.compare_mode:
            minimum, maximum = self._part_bounds[self.framed_part]
            center = (minimum + maximum) * 0.5
            extent = maximum - minimum
            span = max(float(extent[0]), float(extent[1]), float(extent[2]), 0.08)
            distance = max(0.24, span * 2.35) / self.zoom
            target = QVector3D(float(center[0]), float(center[1]), float(center[2]))
        elif self._part_bounds:
            visible_bounds = [
                bounds for index, bounds in self._part_bounds.items() if index not in self.hidden_parts
            ]
            if visible_bounds:
                minimum = np.min(np.vstack([bounds[0] for bounds in visible_bounds]), axis=0)
                maximum = np.max(np.vstack([bounds[1] for bounds in visible_bounds]), axis=0)
                center = (minimum + maximum) * 0.5
                extent = maximum - minimum
                span = max(float(extent[0]), float(extent[1]), float(extent[2]), 0.20)
                compare_span = self._comparison_spacing() * 5.0 if self.compare_mode else span
                distance = max(0.55, compare_span * 1.12, span * 2.15) / self.zoom
                target = QVector3D(float(center[0]), float(center[1]), float(center[2]))
            else:
                distance = 3.6 / self.zoom
                target = QVector3D(0.0, self._model_height * 0.48, 0.0)
        else:
            compare_span = self._comparison_spacing() * 5.0 if self.compare_mode else max(self._model_width, 1.0)
            distance = max(3.6, compare_span * 1.05, self._model_height * 2.0) / self.zoom
            target = QVector3D(0.0, self._model_height * 0.48, 0.0)
        horizontal = math.cos(self.pitch) * distance
        camera = QVector3D(
            math.sin(self.yaw) * horizontal,
            target.y() + math.sin(self.pitch) * distance,
            math.cos(self.yaw) * horizontal,
        )
        projection = QMatrix4x4()
        projection.perspective(38.0, max(self.width(), 1) / max(self.height(), 1), 0.02, 100.0)
        view = QMatrix4x4()
        view.lookAt(camera, target, QVector3D(0.0, 1.0, 0.0))
        return projection, view, camera

    def _comparison_spacing(self) -> float:
        return max(self._model_width * 1.28, 0.85)

    def _model_offsets(self) -> list[float]:
        if not self.compare_mode:
            return [0.0]
        spacing = self._comparison_spacing()
        return [value * spacing for value in (-2.0, -1.0, 0.0, 1.0, 2.0)]

    def _draw_floor(self) -> None:
        assert self._program is not None and self._floor_vao is not None and self._gl is not None
        floor_model = QMatrix4x4()
        floor_model.translate(0.0, self._floor_height, 0.0)
        self._program.setUniformValue("u_model", floor_model)
        self._program.setUniformValue(self._program.uniformLocation("u_mode"), 1)
        self._floor_vao.bind()
        self._gl.glDrawArrays(GL_TRIANGLES, 0, self._floor_vertex_count)
        self._floor_vao.release()

    def _draw_models(self) -> None:
        assert self._program is not None and self._model_vao is not None and self._gl is not None
        self._program.setUniformValue("u_base_texture", 0)
        self._program.setUniformValue(self._program.uniformLocation("u_uv_flip"), int(self.uv_flip_bits))
        self._model_vao.bind()
        if self.wireframe:
            self._gl.glPolygonMode(GL_FRONT_AND_BACK, GL_LINE)
        for offset in self._model_offsets():
            for part_index, start, count in self._part_ranges:
                if part_index in self.hidden_parts:
                    continue
                placement = QMatrix4x4()
                placement.translate(offset, 0.002, 0.0)
                model = placement * self._part_model_matrix(part_index)
                self._program.setUniformValue("u_model", model)
                texture = self._gl_textures.get(self._part_texture_slots.get(part_index, -1))
                if self.selected_bone:
                    mode = 6
                elif texture is not None:
                    if self.material_lit:
                        mode = 4 if part_index == self.selected_part else 0
                    else:
                        mode = 8 if part_index == self.selected_part else 7
                else:
                    mode = 5 if part_index == self.selected_part else 3
                self._program.setUniformValue(self._program.uniformLocation("u_mode"), int(mode))
                if texture is not None:
                    texture.bind(0)
                self._gl.glDrawArrays(GL_TRIANGLES, start, count)
                if texture is not None:
                    texture.release(0)
        if self.wireframe:
            self._gl.glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)
        self._model_vao.release()

    def _part_view_matrix(self, index: int) -> np.ndarray:
        if not 0 <= index < len(self.parts):
            return np.eye(4, dtype=float)
        source = np.asarray(self.parts[index].transform, dtype=float)
        inverse = np.linalg.inv(self._source_to_normalized)
        return self._source_to_normalized @ source @ inverse

    def _part_model_matrix(self, index: int) -> QMatrix4x4:
        return QMatrix4x4(self._part_view_matrix(index).reshape(-1).tolist())

    def _refresh_part_bounds(self, index: int) -> None:
        bounds = self._part_base_bounds.get(index)
        if bounds is None:
            return
        minimum, maximum = bounds
        corners = np.asarray(
            [
                (x, y, z, 1.0)
                for x in (minimum[0], maximum[0])
                for y in (minimum[1], maximum[1])
                for z in (minimum[2], maximum[2])
            ],
            dtype=float,
        )
        transformed = (self._part_view_matrix(index) @ corners.T).T[:, :3]
        self._part_bounds[index] = (transformed.min(axis=0), transformed.max(axis=0))

    def _draw_skeletons(self) -> None:
        assert self._program is not None and self._skeleton_vao is not None and self._gl is not None
        self._program.setUniformValue(self._program.uniformLocation("u_mode"), 2)
        self._gl.glDisable(GL_DEPTH_TEST)
        self._gl.glLineWidth(3.0)
        self._skeleton_vao.bind()
        for offset in self._model_offsets():
            model = QMatrix4x4()
            model.translate(offset, 0.0, 0.0)
            self._program.setUniformValue("u_model", model)
            self._gl.glDrawArrays(GL_LINES, 0, self._skeleton_vertex_count)
            self._gl.glPointSize(7.0)
            self._gl.glDrawArrays(GL_POINTS, 0, self._skeleton_vertex_count)
        self._skeleton_vao.release()
        self._gl.glEnable(GL_DEPTH_TEST)

    def _pick_part(self, x: float, y: float) -> int:
        if not self._part_bounds or self.width() <= 0 or self.height() <= 0:
            return -1
        projection, view, _camera = self._camera_matrices()
        inverse, invertible = (projection * view).inverted()
        if not invertible:
            return -1
        ndc_x = 2.0 * x / self.width() - 1.0
        ndc_y = 1.0 - 2.0 * y / self.height()
        near = inverse * QVector4D(ndc_x, ndc_y, -1.0, 1.0)
        far = inverse * QVector4D(ndc_x, ndc_y, 1.0, 1.0)
        if abs(near.w()) < 1e-8 or abs(far.w()) < 1e-8:
            return -1
        origin = np.asarray((near.x() / near.w(), near.y() / near.w(), near.z() / near.w()), dtype=float)
        far_point = np.asarray((far.x() / far.w(), far.y() / far.w(), far.z() / far.w()), dtype=float)
        direction = far_point - origin
        direction /= max(float(np.linalg.norm(direction)), 1e-12)
        best_index, best_distance = -1, float("inf")
        for part_index, (minimum, maximum) in self._part_bounds.items():
            if part_index in self.hidden_parts:
                continue
            distance = self._ray_box_distance(origin, direction, minimum, maximum)
            if distance is not None and distance < best_distance:
                best_index, best_distance = part_index, distance
        return best_index

    @staticmethod
    def _ray_box_distance(
        origin: np.ndarray,
        direction: np.ndarray,
        minimum: np.ndarray,
        maximum: np.ndarray,
    ) -> float | None:
        safe_direction = np.where(np.abs(direction) < 1e-10, np.copysign(1e-10, direction + 1e-20), direction)
        first = (minimum - origin) / safe_direction
        second = (maximum - origin) / safe_direction
        near = float(np.max(np.minimum(first, second)))
        far = float(np.min(np.maximum(first, second)))
        if far < max(near, 0.0):
            return None
        return max(near, 0.0)

    def _draw_qt_overlay(self) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(7, 11, 17, 220))
        painter.drawRoundedRect(QRectF(14, 14, 210, 30), 6, 6)
        painter.setPen(QColor("#a6b5c8"))
        font = painter.font()
        font.setPointSize(8)
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.drawText(QRectF(25, 14, 188, 30), Qt.AlignmentFlag.AlignVCenter, self.label[:30])

        if self.mesh is None and not self.skeleton:
            painter.setPen(QPen(QColor("#334358"), 1))
            painter.setBrush(QColor(11, 17, 25, 225))
            box = QRectF(self.width() / 2 - 185, self.height() / 2 - 72, 370, 144)
            painter.drawRoundedRect(box, 12, 12)
            painter.setPen(QColor("#d4dce7"))
            font.setPointSize(12)
            painter.setFont(font)
            painter.drawText(QRectF(box.x() + 20, box.y() + 25, box.width() - 40, 28), Qt.AlignmentFlag.AlignCenter, "GPU CHARACTER FITTING VIEWPORT")
            painter.setPen(QColor("#7e8da1"))
            font.setPointSize(9)
            font.setWeight(QFont.Weight.Normal)
            painter.setFont(font)
            painter.drawText(
                QRectF(box.x() + 34, box.y() + 64, box.width() - 68, 54),
                Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                "Drop an FBX, GLB or OBJ. FBX is converted read-only through Blender and appears here automatically.",
            )
        else:
            status = "OFFICIAL REST RIG • EXACT 31-BONE HIERARCHY" if self.mesh is None else "PBR TEXTURE • UV MATERIAL"
            if self.selected_part >= 0:
                status = f"SELECTED • {self.parts[self.selected_part].name[:24]}"
            if self.selected_bone:
                status = f"WEIGHT HEATMAP • {self.selected_bone[:25]}"
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(7, 11, 17, 220))
            width = min(330, max(190, len(status) * 7 + 30))
            painter.drawRoundedRect(QRectF(self.width() - width - 14, self.height() - 44, width, 30), 6, 6)
            painter.setPen(QColor("#66b3ff") if not self.selected_bone else QColor("#ffbd4b"))
            painter.drawText(QRectF(self.width() - width, self.height() - 44, width - 20, 30), Qt.AlignmentFlag.AlignVCenter, status)

            painter.setPen(QColor("#718095"))
            font.setPointSize(8)
            font.setWeight(QFont.Weight.Medium)
            painter.setFont(font)
            painter.drawText(QRectF(18, self.height() - 42, 310, 24), Qt.AlignmentFlag.AlignVCenter, "CLICK  SELECT    •    DRAG  ORBIT    •    WHEEL  ZOOM")
        painter.end()
