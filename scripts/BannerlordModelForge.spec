# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


project_root = Path(SPECPATH).resolve().parent
package_root = project_root / "src" / "bannerlord_model_forge"
qt_root = project_root / ".venv" / "Lib" / "site-packages" / "PySide6"

analysis = Analysis(
    [str(package_root / "exe_entry.py")],
    pathex=[str(project_root / "src")],
    binaries=[
        (str(qt_root / name), ".")
        for name in (
            "VCRUNTIME140.dll",
            "VCRUNTIME140_1.dll",
            "MSVCP140.dll",
            "MSVCP140_1.dll",
            "MSVCP140_2.dll",
        )
    ] + [
        (str(plugin), f"PySide6/plugins/{plugin_group}")
        for plugin_group in ("assetimporters", "sceneparsers")
        for plugin in (qt_root / "plugins" / plugin_group).glob("*.dll")
    ],
    datas=[
        (str(package_root / "blender_bridge.py"), "bannerlord_model_forge"),
        (str(package_root / "blender_skeleton_preview.py"), "bannerlord_model_forge"),
        (str(package_root / "blender_skeleton_data.py"), "bannerlord_model_forge"),
        (str(package_root / "material_viewport.qml"), "bannerlord_model_forge"),
    ],
    hiddenimports=[
        "fast_simplification",
        "networkx",
        "PySide6.QtQuick",
        "PySide6.QtQuickWidgets",
        "PySide6.QtQuick3D",
    ],
    excludes=["pytest", "_pytest", "pytest_cov", "coverage", "pygments", "tkinterdnd2"],
    noarchive=False,
    optimize=0,
)

# Some development hosts expose Poppler's Unix-style ICU DLLs on PATH. QtCore
# on Windows must use the Windows ICU shim; bundling Poppler's copies makes the
# executable fail before the first window can be created.
analysis.binaries = [
    item
    for item in analysis.binaries
    if "\\poppler\\library\\bin\\" not in item[1].lower()
]

pyz = PYZ(analysis.pure)
exe = EXE(
    pyz,
    analysis.scripts,
    analysis.binaries,
    analysis.datas,
    [],
    name="Bannerlord Model Forge",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)
