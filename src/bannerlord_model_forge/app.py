from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from tkinterdnd2 import DND_FILES, TkinterDnD

from .blender_backend import detect_blender
from .config import PRESETS, project_root
from .game_install import inspect_game_install
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


class ForgeApp:
    def __init__(self, root: TkinterDnD.Tk) -> None:
        self.root = root
        self.root.title("Bannerlord Model Forge")
        self.root.geometry("980x760")
        self.root.minsize(820, 650)
        self.root.configure(bg=COLORS["bg"])
        self.messages: queue.Queue[tuple[str, object]] = queue.Queue()
        self.source_var = tk.StringVar()
        self.preset_var = tk.StringVar(value=PRESETS["body"].label)
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

        self.log = tk.Text(outer, height=13, bg="#0b0f16", fg="#cbd4e1", insertbackground="white", relief="flat", padx=14, pady=12, font=("Cascadia Mono", 9), state="disabled")
        self.log.pack(fill="both", expand=True)
        self._log("Files are always written to this project's output folder. Source and game files remain unchanged.")

    def _set_source(self, value: str) -> None:
        self.source_var.set(str(Path(value).expanduser()))

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
        self.target_var.set(PRESETS[self._preset_key()].triangle_target)

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
