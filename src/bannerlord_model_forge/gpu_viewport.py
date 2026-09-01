from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
from PySide6.QtCore import QPoint, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QMatrix4x4, QMouseEvent, QPainter, QPen, QSurfaceFormat, QVector3D, QWheelEvent
from PySide6.QtOpenGL import (
    QOpenGLBuffer,
    QOpenGLFunctions_3_3_Core,
    QOpenGLShader,
    QOpenGLShaderProgram,
    QOpenGLVertexArrayObject,
)
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import QSizePolicy

from .config import BONE_REGION_PATTERNS, PRESETS


GL_FLOAT = 0x1406
GL_TRIANGLES = 0x0004
GL_LINES = 0x0001
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

uniform mat4 u_model;
uniform mat4 u_view;
uniform mat4 u_projection;

out vec3 v_world;
out vec3 v_normal;
out vec3 v_color;
out float v_weight;

void main() {
    vec4 world = u_model * vec4(a_position, 1.0);
    v_world = world.xyz;
    v_normal = normalize(mat3(transpose(inverse(u_model))) * a_normal);
    v_color = a_color;
    v_weight = a_weight;
    gl_Position = u_projection * u_view * world;
}
"""


FRAGMENT_SHADER = """#version 330 core
in vec3 v_world;
in vec3 v_normal;
in vec3 v_color;
in float v_weight;

uniform int u_mode;
uniform bool u_heatmap;
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
    float specular = pow(max(dot(N, halfVector), 0.0), 44.0);

    vec3 base = v_color;
    if (u_heatmap) {
        vec3 cold = vec3(0.025, 0.12, 0.34);
        vec3 hot = vec3(1.0, 0.21, 0.025);
        vec3 peak = vec3(1.0, 0.88, 0.08);
        base = v_weight < 0.55
            ? mix(cold, hot, v_weight / 0.55)
            : mix(hot, peak, (v_weight - 0.55) / 0.45);
    }
    vec3 light = vec3(0.16) + vec3(0.67, 0.79, 0.98) * key + vec3(0.35, 0.16, 0.075) * fill;
    vec3 color = base * light + vec3(0.075, 0.19, 0.39) * rim + vec3(0.58) * specular;
    fragColor = vec4(linear_to_srgb(color), 1.0);
}
"""


def _neutral_vertex_colors(mesh, count: int) -> np.ndarray:
    fallback = np.tile(np.asarray((0.16, 0.205, 0.265), dtype=np.float32), (count, 1))
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
        self.yaw = math.radians(22.0)
        self.pitch = math.radians(7.0)
        self.zoom = 1.0
        self.last_mouse: QPoint | None = None
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
        self._mesh_interleaved = np.empty((0, 10), dtype=np.float32)
        self._skeleton_interleaved = np.empty((0, 10), dtype=np.float32)
        self._model_height = 2.0
        self._model_width = 0.8
        self._normalization_scale = 1.0
        self._normalization_origin = np.zeros(3, dtype=float)
        self._axis_order = [0, 2, 1]

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
        self._prepare_cpu_geometry()
        self._upload_if_ready()
        self.bone_options_changed.emit(bones, self.weights_provisional)
        self.statistics_changed.emit(
            {
                "vertices": len(mesh.vertices),
                "triangles": len(mesh.faces),
                "bones": len(self.skeleton),
                "weights": bool(bones),
            }
        )
        self.set_view(math.radians(22.0), math.radians(7.0))

    def clear(self) -> None:
        self.mesh = None
        self.skeleton = []
        self.weights = []
        self._mesh_interleaved = np.empty((0, 10), dtype=np.float32)
        self._skeleton_interleaved = np.empty((0, 10), dtype=np.float32)
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
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseReleaseEvent(self, _event: QMouseEvent) -> None:  # type: ignore[override]
        self.last_mouse = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        if self.last_mouse is None:
            return
        point = event.position().toPoint()
        delta = point - self.last_mouse
        self.last_mouse = point
        self.yaw -= delta.x() * 0.009
        self.pitch = float(np.clip(self.pitch + delta.y() * 0.009, math.radians(-75), math.radians(75)))
        self.update()

    def wheelEvent(self, event: QWheelEvent) -> None:  # type: ignore[override]
        self.zoom = float(np.clip(self.zoom * (1.12 if event.angleDelta().y() > 0 else 0.89), 0.35, 4.5))
        self.update()

    def _prepare_cpu_geometry(self) -> None:
        if self.mesh is None or not len(self.mesh.faces):
            return
        vertices = np.asarray(self.mesh.vertices, dtype=np.float64)
        faces = np.asarray(self.mesh.faces, dtype=np.uint32)
        extents = np.ptp(vertices, axis=0)
        up_axis = int(np.argmax(extents))
        horizontal = [axis for axis in range(3) if axis != up_axis]
        horizontal.sort(key=lambda axis: extents[axis], reverse=True)
        self._axis_order = [horizontal[0], up_axis, horizontal[1]]
        aligned = vertices[:, self._axis_order]
        minimum = aligned.min(axis=0)
        maximum = aligned.max(axis=0)
        self._normalization_origin = np.asarray(((minimum[0] + maximum[0]) * 0.5, minimum[1], (minimum[2] + maximum[2]) * 0.5))
        height = max(float(maximum[1] - minimum[1]), 1e-6)
        self._normalization_scale = 2.0 / height
        positions = ((aligned - self._normalization_origin) * self._normalization_scale).astype(np.float32)
        self._model_height = max(float(np.ptp(positions[:, 1])), 0.25)
        self._model_width = max(float(np.ptp(positions[:, 0])), 0.25)

        normals = _crease_aware_normals(aligned, np.asarray(self.mesh.faces, dtype=int))
        colors = _neutral_vertex_colors(self.mesh, len(vertices))
        weights = np.zeros((len(vertices), 1), dtype=np.float32)
        if self.selected_bone and len(self.weights) == len(vertices):
            weights[:, 0] = np.asarray([float(row.get(self.selected_bone, 0.0)) for row in self.weights], dtype=np.float32)
        per_vertex = np.column_stack((positions, normals, colors, weights)).astype(np.float32)
        self._mesh_interleaved = per_vertex[faces.reshape(-1)].copy()

        skeleton_rows: list[np.ndarray] = []
        for bone in self.skeleton:
            name = str(bone.get("name", "")).lower()
            focused = not self.focus_patterns or any(pattern in name for pattern in self.focus_patterns)
            for field in ("head", "tail"):
                point = np.asarray(bone.get(field, [0.0, 0.0, 0.0]), dtype=float)[self._axis_order]
                position = (point - self._normalization_origin) * self._normalization_scale
                skeleton_rows.append(
                    np.asarray((*position, 0.0, 1.0, 0.0, 1.0, 0.27, 0.10, 1.0 if focused else 0.0), dtype=np.float32)
                )
        self._skeleton_interleaved = np.vstack(skeleton_rows) if skeleton_rows else np.empty((0, 10), dtype=np.float32)

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
        stride = 10 * 4
        for location, offset, size in ((0, 0, 3), (1, 3 * 4, 3), (2, 6 * 4, 3), (3, 9 * 4, 1)):
            self._program.enableAttributeArray(location)
            self._program.setAttributeBuffer(location, GL_FLOAT, offset, size, stride)
        self._model_vao.release()
        self._model_vbo.release()
        self._index_count = len(self._mesh_interleaved)

        assert self._skeleton_vao is not None and self._skeleton_vbo is not None
        if not self._skeleton_vao.isCreated():
            self._skeleton_vao.create()
        if not self._skeleton_vbo.isCreated():
            self._skeleton_vbo.create()
        self._skeleton_vao.bind()
        self._skeleton_vbo.bind()
        self._skeleton_vbo.allocate(self._skeleton_interleaved.tobytes(), self._skeleton_interleaved.nbytes)
        for location, offset, size in ((0, 0, 3), (1, 3 * 4, 3), (2, 6 * 4, 3), (3, 9 * 4, 1)):
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
        dark = (0.032, 0.044, 0.061)
        light = (0.115, 0.139, 0.171)
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
        data = np.column_stack((floor, normals, colors, weights)).astype(np.float32)
        self._floor_vao.create()
        self._floor_vbo.create()
        self._program.bind()
        self._floor_vao.bind()
        self._floor_vbo.bind()
        self._floor_vbo.allocate(data.tobytes(), data.nbytes)
        self._floor_vertex_count = len(data)
        stride = 10 * 4
        for location, offset, size in ((0, 0, 3), (1, 3 * 4, 3), (2, 6 * 4, 3), (3, 9 * 4, 1)):
            self._program.enableAttributeArray(location)
            self._program.setAttributeBuffer(location, GL_FLOAT, offset, size, stride)
        self._floor_vao.release()
        self._floor_vbo.release()
        self._program.release()

    def _camera_matrices(self) -> tuple[QMatrix4x4, QMatrix4x4, QVector3D]:
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
        identity = QMatrix4x4()
        self._program.setUniformValue("u_model", identity)
        self._program.setUniformValue("u_mode", 1)
        self._program.setUniformValue("u_heatmap", False)
        self._floor_vao.bind()
        self._gl.glDrawArrays(GL_TRIANGLES, 0, self._floor_vertex_count)
        self._floor_vao.release()

    def _draw_models(self) -> None:
        assert self._program is not None and self._model_vao is not None and self._gl is not None
        self._program.setUniformValue("u_mode", 0)
        self._program.setUniformValue("u_heatmap", bool(self.selected_bone))
        self._model_vao.bind()
        if self.wireframe:
            self._gl.glPolygonMode(GL_FRONT_AND_BACK, GL_LINE)
        for offset in self._model_offsets():
            model = QMatrix4x4()
            model.translate(offset, 0.002, 0.0)
            self._program.setUniformValue("u_model", model)
            self._gl.glDrawArrays(GL_TRIANGLES, 0, self._index_count)
        if self.wireframe:
            self._gl.glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)
        self._model_vao.release()

    def _draw_skeletons(self) -> None:
        assert self._program is not None and self._skeleton_vao is not None and self._gl is not None
        self._program.setUniformValue("u_mode", 2)
        self._program.setUniformValue("u_heatmap", False)
        self._gl.glDisable(GL_DEPTH_TEST)
        self._gl.glLineWidth(2.2)
        self._skeleton_vao.bind()
        for offset in self._model_offsets():
            model = QMatrix4x4()
            model.translate(offset, 0.0, 0.0)
            self._program.setUniformValue("u_model", model)
            self._gl.glDrawArrays(GL_LINES, 0, self._skeleton_vertex_count)
        self._skeleton_vao.release()
        self._gl.glEnable(GL_DEPTH_TEST)

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

        if self.mesh is None:
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
            status = "GPU • SMOOTH SHADED"
            if self.selected_bone:
                status = f"WEIGHT HEATMAP • {self.selected_bone[:25]}"
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(7, 11, 17, 220))
            width = min(330, max(190, len(status) * 7 + 30))
            painter.drawRoundedRect(QRectF(self.width() - width - 14, self.height() - 44, width, 30), 6, 6)
            painter.setPen(QColor("#66b3ff") if not self.selected_bone else QColor("#ffbd4b"))
            painter.drawText(QRectF(self.width() - width, self.height() - 44, width - 20, 30), Qt.AlignmentFlag.AlignVCenter, status)
        painter.end()
