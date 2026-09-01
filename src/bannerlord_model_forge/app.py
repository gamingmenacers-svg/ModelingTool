from __future__ import annotations

import os
import json
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import numpy as np
from PIL import Image, ImageDraw, ImageTk
from tkinterdnd2 import DND_FILES, TkinterDnD

from .blender_backend import detect_blender
from .config import BONE_REGION_PATTERNS, PRESETS, project_root
from .game_install import inspect_game_install
from .mesh_io import load_mesh
from .pipeline import run_pipeline
from .sample import create_sample


COLORS = {
    "bg": "#11151d",
    "panel": "#1a202b",
    "panel2": "#222a37",
    "text": "#f3f6fa",
    "muted": "#a4afbf",
    "accent": "#4ea4ff",
    "good": "#61d095",
    "warning": "#f4bd62",
}


class ModelViewport(ttk.Frame):
    """Small interactive software viewport for mesh, skeleton, and weight inspection."""

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent, style="Panel.TFrame", padding=10)
        self.mesh = None
        self.skeleton: list[dict[str, object]] = []
        self.weights: list[dict[str, float]] = []
        self.weights_provisional = False
        self.focus_patterns: tuple[str, ...] = ()
        self.yaw = 0.55
        self.pitch = -0.25
        self.zoom = 1.0
        self.last_mouse: tuple[int, int] | None = None
        self.photo: ImageTk.PhotoImage | None = None
        self.wireframe_var = tk.BooleanVar(value=True)
        self.skeleton_var = tk.BooleanVar(value=True)
        self.bone_var = tk.StringVar(value="Weight heatmap: off")
        self.status_var = tk.StringVar(value="Choose a model to preview it here.")

        header = ttk.Frame(self, style="Panel.TFrame")
        header.pack(fill="x", pady=(0, 7))
        ttk.Label(header, text="Rig Inspector", style="Panel.TLabel", font=("Segoe UI Semibold", 12)).pack(side="left")
        ttk.Button(header, text="Front", command=lambda: self._view(0.0, 0.0)).pack(side="right", padx=2)
        ttk.Button(header, text="Side", command=lambda: self._view(1.5708, 0.0)).pack(side="right", padx=2)
        ttk.Button(header, text="3/4", command=lambda: self._view(0.55, -0.25)).pack(side="right", padx=2)

        self.canvas = tk.Canvas(self, width=440, height=410, bg="#0b0f16", highlightthickness=0, cursor="fleur")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<ButtonPress-1>", self._mouse_down)
        self.canvas.bind("<B1-Motion>", self._mouse_drag)
        self.canvas.bind("<MouseWheel>", self._mouse_wheel)
        self.canvas.bind("<Configure>", lambda _event: self.redraw())

        controls = ttk.Frame(self, style="Panel.TFrame")
        controls.pack(fill="x", pady=(8, 0))
        ttk.Checkbutton(controls, text="Wireframe", variable=self.wireframe_var, command=self.redraw).pack(side="left")
        ttk.Checkbutton(controls, text="Skeleton", variable=self.skeleton_var, command=self.redraw).pack(side="left", padx=8)
        self.bone_combo = ttk.Combobox(controls, state="disabled", textvariable=self.bone_var, width=24)
        self.bone_combo.pack(side="right")
        self.bone_combo.bind("<<ComboboxSelected>>", lambda _event: self.redraw())
        ttk.Label(self, textvariable=self.status_var, style="Panel.TLabel", wraplength=430).pack(fill="x", pady=(7, 0))

    def set_model(
        self,
        mesh,
        skeleton_path: Path | None = None,
        weights_path: Path | None = None,
        label: str = "Model",
        preset_key: str | None = None,
    ) -> None:
        self.mesh = mesh
        self.skeleton = []
        if skeleton_path and skeleton_path.is_file():
            data = json.loads(skeleton_path.read_text(encoding="utf-8"))
            self.skeleton = list(data.get("bones", []))
        self.weights = []
        self.weights_provisional = False
        self.focus_patterns = (
            BONE_REGION_PATTERNS.get(PRESETS[preset_key].skeleton_region, ())
            if preset_key in PRESETS
            else ()
        )
        bones: list[str] = []
        if weights_path and weights_path.is_file():
            data = json.loads(weights_path.read_text(encoding="utf-8"))
            self.weights = list(data.get("weights", []))
            self.weights_provisional = bool(data.get("provisional", False))
            bones = [str(name) for name in data.get("bones", [])]
        if bones and len(self.weights) == len(mesh.vertices):
            values = ["Weight heatmap: off"] + bones
            self.bone_combo.configure(values=values, state="readonly")
            self.bone_var.set(values[0])
        else:
            self.bone_combo.configure(values=["Weight heatmap: off"], state="disabled")
            self.bone_var.set("Weight heatmap: off")
        skeleton_text = f" • {len(self.skeleton)} bones overlaid" if self.skeleton else " • no skeleton overlay"
        if bones:
            weight_text = " • provisional auto-weights available" if self.weights_provisional else " • reference-transferred weights available"
        else:
            weight_text = " • no skin weights"
        self.status_var.set(f"{label}: {len(mesh.vertices):,} vertices / {len(mesh.faces):,} triangles{skeleton_text}{weight_text}. Drag to orbit; wheel to zoom.")
        self._view(0.55, -0.25)

    def _view(self, yaw: float, pitch: float) -> None:
        self.yaw, self.pitch, self.zoom = yaw, pitch, 1.0
        self.redraw()

    def _mouse_down(self, event: tk.Event) -> None:
        self.last_mouse = (event.x, event.y)

    def _mouse_drag(self, event: tk.Event) -> None:
        if self.last_mouse is None:
            return
        dx, dy = event.x - self.last_mouse[0], event.y - self.last_mouse[1]
        self.last_mouse = (event.x, event.y)
        self.yaw += dx * 0.012
        self.pitch = float(np.clip(self.pitch + dy * 0.012, -1.45, 1.45))
        self.redraw()

    def _mouse_wheel(self, event: tk.Event) -> None:
        self.zoom = float(np.clip(self.zoom * (1.12 if event.delta > 0 else 0.89), 0.3, 4.0))
        self.redraw()

    def redraw(self) -> None:
        width = max(100, self.canvas.winfo_width())
        height = max(100, self.canvas.winfo_height())
        image = Image.new("RGB", (width, height), (11, 15, 22))
        if self.mesh is None or not len(self.mesh.faces):
            draw = ImageDraw.Draw(image)
            draw.text((24, 28), "Model viewport\n\nDrop a model, choose its armour piece,\nthen Analyze and prepare.", fill=(170, 181, 198), spacing=7)
            self._present(image)
            return

        vertices = np.asarray(self.mesh.vertices, dtype=float)
        faces = np.asarray(self.mesh.faces, dtype=int)
        extents = np.ptp(vertices, axis=0)
        up_axis = int(np.argmax(extents))
        remaining = [axis for axis in range(3) if axis != up_axis]
        remaining.sort(key=lambda axis: extents[axis], reverse=True)
        axis_order = [remaining[0], up_axis, remaining[1]]
        aligned = vertices[:, axis_order]

        skeleton_segments: list[tuple[np.ndarray, bool]] = []
        if self.skeleton_var.get():
            for bone in self.skeleton:
                head = np.asarray(bone.get("head", [0, 0, 0]), dtype=float)[axis_order]
                tail = np.asarray(bone.get("tail", [0, 0, 0]), dtype=float)[axis_order]
                name = str(bone.get("name", "")).lower()
                focused = not self.focus_patterns or any(pattern in name for pattern in self.focus_patterns)
                skeleton_segments.append((np.stack((head, tail)), focused))
        combined = [aligned]
        if skeleton_segments:
            combined.append(np.concatenate([segment for segment, _focused in skeleton_segments], axis=0))
        bounds_points = np.concatenate(combined, axis=0)
        center = (bounds_points.min(axis=0) + bounds_points.max(axis=0)) * 0.5

        cy, sy = np.cos(self.yaw), np.sin(self.yaw)
        cp, sp = np.cos(self.pitch), np.sin(self.pitch)
        yaw_matrix = np.asarray([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
        pitch_matrix = np.asarray([[1, 0, 0], [0, cp, -sp], [0, sp, cp]])
        rotation = pitch_matrix @ yaw_matrix
        rotated = (aligned - center) @ rotation.T
        rotated_skeleton = [((segment - center) @ rotation.T, focused) for segment, focused in skeleton_segments]
        rotated_bounds = [rotated] + [segment for segment, _focused in rotated_skeleton]
        span_points = np.concatenate(rotated_bounds, axis=0)
        span = max(float(np.ptp(span_points[:, 0])), float(np.ptp(span_points[:, 1])), 1e-9)
        scale = min(width, height) * 0.80 / span * self.zoom

        projected = np.empty((len(rotated), 2), dtype=float)
        projected[:, 0] = rotated[:, 0] * scale + width / 2
        projected[:, 1] = -rotated[:, 1] * scale + height / 2
        if len(faces) > 6500:
            face_indices = np.linspace(0, len(faces) - 1, 6500).astype(int)
            draw_faces = faces[face_indices]
        else:
            face_indices = np.arange(len(faces))
            draw_faces = faces
        triangles = rotated[draw_faces]
        depth = triangles[:, :, 2].mean(axis=1)
        order = np.argsort(depth)
        normals = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
        normal_length = np.linalg.norm(normals, axis=1)
        normal_length[normal_length == 0] = 1
        normals /= normal_length[:, None]
        brightness = np.clip(0.28 + 0.72 * np.abs(normals @ np.asarray((-0.35, 0.55, 0.75))), 0.2, 1.0)
        selected_bone = self.bone_var.get()
        heatmap = selected_bone != "Weight heatmap: off" and len(self.weights) == len(vertices)
        vertex_weights = None
        if heatmap:
            vertex_weights = np.asarray([float(row.get(selected_bone, 0.0)) for row in self.weights])
        draw = ImageDraw.Draw(image)
        for draw_index in order:
            face = draw_faces[draw_index]
            polygon = [tuple(projected[vertex]) for vertex in face]
            if vertex_weights is not None:
                weight = float(vertex_weights[face].mean())
                cold = np.asarray((27, 58, 98), dtype=float)
                hot = np.asarray((255, 191, 45), dtype=float)
                color = tuple(np.clip(cold * (1.0 - weight) + hot * weight, 0, 255).astype(int))
            else:
                color = tuple(np.clip(np.asarray((65, 154, 247)) * brightness[draw_index], 0, 255).astype(int))
            outline = (20, 27, 38) if self.wireframe_var.get() else color
            draw.polygon(polygon, fill=color, outline=outline)
        for segment, focused in rotated_skeleton:
            points = [
                (segment[index, 0] * scale + width / 2, -segment[index, 1] * scale + height / 2)
                for index in range(2)
            ]
            line_color = (255, 67, 36) if focused else (97, 105, 119)
            draw.line(points, fill=line_color, width=3 if focused else 1)
            for point in points:
                radius = 2 if focused else 1
                joint_color = (255, 216, 94) if focused else (122, 130, 144)
                draw.ellipse((point[0] - radius, point[1] - radius, point[0] + radius, point[1] + radius), fill=joint_color)
        badge = (
            "PROVISIONAL WEIGHTS"
            if self.weights and self.weights_provisional
            else "TRANSFERRED WEIGHTS"
            if self.weights
            else "ALIGNMENT GUIDE"
        )
        draw.rounded_rectangle((12, 12, 190, 38), radius=8, fill=(7, 10, 16))
        draw.text((22, 20), badge, fill=(244, 190, 74) if self.weights else (170, 181, 198))
        self._present(image)

    def _present(self, image: Image.Image) -> None:
        self.photo = ImageTk.PhotoImage(image)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=self.photo, anchor="nw")


class ForgeApp:
    def __init__(self, root: TkinterDnD.Tk) -> None:
        self.root = root
        self.root.title("Bannerlord Model Forge")
        self.root.geometry("1240x820")
        self.root.minsize(980, 700)
        self.root.configure(bg=COLORS["bg"])
        self.messages: queue.Queue[tuple[str, object]] = queue.Queue()
        self.source_var = tk.StringVar()
        self.preset_var = tk.StringVar(value=PRESETS["body"].label)
        self.guidance_var = tk.StringVar(value=PRESETS["body"].guidance)
        self.target_var = tk.IntVar(value=PRESETS["body"].triangle_target)
        self.reference_var = tk.StringVar()
        self.weapon_bone_var = tk.StringVar()
        self.weapon_skeleton_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Choose a model to begin.")
        self.output_dir: Path | None = None
        self.advanced_open = False
        self._styles()
        self._build()
        self.root.after(100, self._drain_messages)

    def _styles(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background=COLORS["bg"])
        style.configure("Panel.TFrame", background=COLORS["panel"])
        style.configure("TLabel", background=COLORS["bg"], foreground=COLORS["text"], font=("Segoe UI", 10))
        style.configure("Title.TLabel", font=("Segoe UI Semibold", 25), foreground=COLORS["text"])
        style.configure("Muted.TLabel", foreground=COLORS["muted"])
        style.configure("Panel.TLabel", background=COLORS["panel"], foreground=COLORS["text"])
        style.configure("TButton", font=("Segoe UI Semibold", 10), padding=(16, 9))
        style.configure("Accent.TButton", background=COLORS["accent"], foreground="#07111d")
        style.map("Accent.TButton", background=[("active", "#76b9ff"), ("disabled", "#405268")])
        style.configure("TCombobox", padding=6)

    def _build(self) -> None:
        outer = ttk.Frame(self.root, padding=28)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Bannerlord Model Forge", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            outer,
            text="Prepare armour and weapons for a safe, guided Bannerlord import — no Blender knowledge required.",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(2, 20))

        install = inspect_game_install()
        blender = detect_blender()
        banner = ttk.Frame(outer, style="Panel.TFrame", padding=14)
        banner.pack(fill="x", pady=(0, 16))
        game_text = f"Bannerlord {install.version or 'not found'}  •  Modding Kit {'ready' if install.editor_found else 'missing'}"
        blender_text = f"Blender {'ready' if blender.found else 'optional — not installed'}"
        ttk.Label(banner, text=game_text, style="Panel.TLabel").pack(side="left")
        ttk.Label(banner, text=blender_text, style="Panel.TLabel").pack(side="right")

        self.drop = tk.Frame(outer, bg=COLORS["panel"], highlightbackground="#354155", highlightthickness=2, height=130)
        self.drop.pack(fill="x")
        self.drop.pack_propagate(False)
        tk.Label(self.drop, text="Drop an OBJ, GLB/GLTF, FBX, PLY, or STL here", bg=COLORS["panel"], fg=COLORS["text"], font=("Segoe UI Semibold", 15)).pack(pady=(24, 5))
        tk.Label(self.drop, textvariable=self.source_var, bg=COLORS["panel"], fg=COLORS["muted"], font=("Segoe UI", 9)).pack()
        drop_buttons = ttk.Frame(self.drop, style="Panel.TFrame")
        drop_buttons.pack(pady=10)
        ttk.Button(drop_buttons, text="Browse…", command=self._browse).pack(side="left", padx=5)
        ttk.Button(drop_buttons, text="Use training sample", command=self._sample).pack(side="left", padx=5)
        self.drop.drop_target_register(DND_FILES)
        self.drop.dnd_bind("<<Drop>>", self._on_drop)

        controls = ttk.Frame(outer)
        controls.pack(fill="x", pady=18)
        left = ttk.Frame(controls)
        left.pack(side="left", fill="x", expand=True)
        ttk.Label(left, text="What are you preparing?").pack(anchor="w")
        combo = ttk.Combobox(
            left,
            state="readonly",
            textvariable=self.preset_var,
            values=[preset.label for preset in PRESETS.values()],
            width=28,
        )
        combo.pack(anchor="w", pady=(5, 0))
        combo.bind("<<ComboboxSelected>>", self._preset_changed)
        ttk.Label(left, textvariable=self.guidance_var, style="Muted.TLabel", wraplength=720).pack(anchor="w", pady=(6, 0))
        ttk.Button(controls, text="Advanced ▸", command=self._toggle_advanced).pack(side="right", anchor="s")

        self.advanced = ttk.Frame(outer, style="Panel.TFrame", padding=14)
        ttk.Label(self.advanced, text="Triangle target", style="Panel.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Spinbox(self.advanced, from_=4, to=5_000_000, textvariable=self.target_var, width=14).grid(row=0, column=1, padx=12, sticky="w")
        ttk.Label(self.advanced, text="Weighted reference JSON (armour)", style="Panel.TLabel").grid(row=1, column=0, sticky="w", pady=(10, 0))
        ttk.Entry(self.advanced, textvariable=self.reference_var, width=52).grid(row=1, column=1, padx=12, pady=(10, 0), sticky="ew")
        ttk.Button(self.advanced, text="Choose…", command=self._browse_reference).grid(row=1, column=2, pady=(10, 0))
        ttk.Label(self.advanced, text="Exceptional rigid bone (weapon)", style="Panel.TLabel").grid(row=2, column=0, sticky="w", pady=(10, 0))
        ttk.Entry(self.advanced, textvariable=self.weapon_bone_var, width=30).grid(row=2, column=1, padx=12, pady=(10, 0), sticky="w")
        ttk.Label(self.advanced, text="Weapon skeleton FBX (exception only)", style="Panel.TLabel").grid(row=3, column=0, sticky="w", pady=(10, 0))
        ttk.Entry(self.advanced, textvariable=self.weapon_skeleton_var, width=52).grid(row=3, column=1, padx=12, pady=(10, 0), sticky="ew")
        ttk.Button(self.advanced, text="Choose…", command=self._browse_weapon_skeleton).grid(row=3, column=2, pady=(10, 0))
        self.advanced.columnconfigure(1, weight=1)

        action_row = ttk.Frame(outer)
        action_row.pack(fill="x", pady=(0, 12))
        self.forge_button = ttk.Button(action_row, text="Analyze and prepare", style="Accent.TButton", command=self._start)
        self.forge_button.pack(side="left")
        self.open_button = ttk.Button(action_row, text="Open result folder", state="disabled", command=self._open_output)
        self.open_button.pack(side="left", padx=10)
        ttk.Label(action_row, textvariable=self.status_var, style="Muted.TLabel").pack(side="right")

        workspace = ttk.Panedwindow(outer, orient="horizontal")
        workspace.pack(fill="both", expand=True)
        log_panel = ttk.Frame(workspace)
        self.log = tk.Text(log_panel, height=13, bg="#0b0f16", fg="#cbd4e1", insertbackground="white", relief="flat", padx=14, pady=12, font=("Cascadia Mono", 9), state="disabled")
        self.log.pack(fill="both", expand=True)
        self.viewport = ModelViewport(workspace)
        workspace.add(log_panel, weight=2)
        workspace.add(self.viewport, weight=3)
        self._log("Files are always written to this project's output folder. Source and game files remain unchanged.")

    def _set_source(self, value: str) -> None:
        path = Path(value).expanduser()
        self.source_var.set(str(path))
        if path.suffix.lower() == ".fbx":
            self.viewport.status_var.set("FBX selected. Its interactive preview will appear after safe Blender conversion.")
            return
        if path.is_file():
            threading.Thread(target=self._source_preview_worker, args=(path,), daemon=True).start()

    def _source_preview_worker(self, source: Path) -> None:
        try:
            mesh, _context = load_mesh(source)
            self.messages.put(("preview", (mesh, "Source preview")))
        except Exception as exc:
            self.messages.put(("log", f"Preview unavailable: {exc}"))

    def _result_preview_worker(self, result) -> None:
        try:
            mesh, _context = load_mesh(result.artifacts["prepared_glb"])
            self.messages.put(
                (
                    "result_preview",
                    (
                        mesh,
                        result.artifacts.get("skeleton_viewport_data"),
                        result.artifacts.get("skin_weights"),
                        result.preset_key,
                    ),
                )
            )
        except Exception as exc:
            self.messages.put(("log", f"Rig Inspector could not load the result: {exc}"))

    def _browse(self) -> None:
        selected = filedialog.askopenfilename(filetypes=[("3D models", "*.obj *.glb *.gltf *.fbx *.ply *.stl"), ("All files", "*.*")])
        if selected:
            self._set_source(selected)

    def _browse_reference(self) -> None:
        selected = filedialog.askopenfilename(filetypes=[("Reference manifest", "*.json")])
        if selected:
            self.reference_var.set(selected)

    def _browse_weapon_skeleton(self) -> None:
        selected = filedialog.askopenfilename(filetypes=[("FBX skeleton", "*.fbx")])
        if selected:
            self.weapon_skeleton_var.set(selected)

    def _sample(self) -> None:
        path = create_sample(project_root() / "work" / "samples" / "training_armour.glb")
        self._set_source(str(path))
        self.preset_var.set(PRESETS["body"].label)
        self._preset_changed()
        self._log(f"Generated original training mesh: {path}")

    def _on_drop(self, event: tk.Event) -> None:
        values = self.root.tk.splitlist(event.data)
        if values:
            self._set_source(values[0])

    def _preset_changed(self, _event: object | None = None) -> None:
        preset = PRESETS[self._preset_key()]
        self.target_var.set(preset.triangle_target)
        self.guidance_var.set(preset.guidance)

    def _preset_key(self) -> str:
        selected = self.preset_var.get()
        return next(key for key, preset in PRESETS.items() if preset.label == selected)

    def _toggle_advanced(self) -> None:
        self.advanced_open = not self.advanced_open
        if self.advanced_open:
            self.advanced.pack(fill="x", before=self.forge_button.master, pady=(0, 16))
        else:
            self.advanced.pack_forget()

    def _start(self) -> None:
        source = Path(self.source_var.get())
        if not source.is_file():
            messagebox.showerror("Choose a model", "Drop a model or choose the training sample first.")
            return
        self.forge_button.configure(state="disabled")
        self.open_button.configure(state="disabled")
        self.status_var.set("Working…")
        reference = Path(self.reference_var.get()) if self.reference_var.get().strip() else None
        weapon_bone = self.weapon_bone_var.get().strip() or None
        weapon_skeleton = Path(self.weapon_skeleton_var.get()) if self.weapon_skeleton_var.get().strip() else None
        thread = threading.Thread(
            target=self._worker,
            args=(source, self._preset_key(), self.target_var.get(), reference, weapon_bone, weapon_skeleton),
            daemon=True,
        )
        thread.start()

    def _worker(self, source: Path, preset: str, target: int, reference: Path | None, weapon_bone: str | None, weapon_skeleton: Path | None) -> None:
        try:
            result = run_pipeline(source, preset, target, reference_manifest=reference, weapon_bone=weapon_bone, weapon_skeleton=weapon_skeleton, progress=lambda message: self.messages.put(("log", message)))
            self.messages.put(("done", result))
        except Exception as exc:
            self.messages.put(("error", str(exc)))

    def _drain_messages(self) -> None:
        try:
            while True:
                kind, payload = self.messages.get_nowait()
                if kind == "log":
                    self._log(str(payload))
                elif kind == "done":
                    result = payload
                    self.output_dir = result.output_dir
                    self._log(f"Before → after: {result.before.triangles:,} → {result.after.triangles:,} triangles")
                    self._log(f"Rigging: {result.rigging.status} ({result.rigging.confidence:.0%} confidence)")
                    self.status_var.set("Finished — review the report")
                    self.forge_button.configure(state="normal")
                    self.open_button.configure(state="normal")
                    threading.Thread(target=self._result_preview_worker, args=(result,), daemon=True).start()
                elif kind == "preview":
                    mesh, label = payload
                    self.viewport.set_model(mesh, label=label)
                elif kind == "result_preview":
                    mesh, skeleton_path, weights_path, preset_key = payload
                    self.viewport.set_model(mesh, skeleton_path, weights_path, "Prepared result", preset_key)
                elif kind == "error":
                    self.status_var.set("Could not finish")
                    self.forge_button.configure(state="normal")
                    self._log(f"ERROR: {payload}")
                    messagebox.showerror("Forge stopped", str(payload))
        except queue.Empty:
            pass
        self.root.after(100, self._drain_messages)

    def _log(self, message: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", message + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _open_output(self) -> None:
        if self.output_dir:
            os.startfile(self.output_dir)  # type: ignore[attr-defined]


def main() -> None:
    root = TkinterDnD.Tk()
    ForgeApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
