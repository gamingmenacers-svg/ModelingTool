# Third-party dependencies and licenses

The project code is MIT licensed. Runtime dependencies are installed from PyPI into a local virtual environment and are not vendored.

| Dependency | Purpose | License family |
| --- | --- | --- |
| NumPy | Array math and deterministic geometry metrics | BSD-3-Clause |
| Pillow | Preview PNG rendering | HPND |
| trimesh | Mesh import, inspection, export, and geometry operations | MIT |
| fast-simplification | Quadric-error mesh simplification | MIT |
| NetworkX | Connected-component graph operations used by mesh repair | BSD-3-Clause |
| tkinterdnd2 / TkDND | Desktop drag-and-drop integration | MIT / BSD-style |
| pytest, pytest-cov | Development tests only | MIT |

Optional external tools:

- Blender is GPL-licensed and is neither embedded nor redistributed. If installed by the user, it runs as a separate background process for FBX conversion/export operations.
- Mount & Blade II: Bannerlord and its Modding Kit remain TaleWorlds products. The app only reads allowlisted local metadata and detects an official skeleton reference in place. No TaleWorlds asset is included in this repository or generated outputs.

Before distribution, regenerate a locked dependency report for the exact released versions and include their complete notices.
