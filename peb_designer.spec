# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for PEB Designer (Windows onedir distribution)

import sys
from pathlib import Path

block_cipher = None
root = Path(SPECPATH)

a = Analysis(
    [str(root / "run_peb_designer.py")],
    pathex=[str(root)],
    binaries=[],
    datas=[
        (str(root / "app" / "gui" / "assets"), "app/gui/assets"),
        (str(root / "data"), "data"),
        (str(root / "examples" / "templates" / "std"), "examples/templates/std"),
        (str(root / "examples" / "audited"), "examples/audited"),
        (str(root / "docs" / "SIDEBAR_STAAD_AUDIT.md"), "docs"),
        (str(root / "docs" / "REFERENCE_STAAD_UPDATE.md"), "docs"),
        (str(root / "docs" / "HOW_TO_TEST.txt"), "."),
    ],
    hiddenimports=[
        "PySide6",
        "shiboken6",
        "pyvista",
        "pyvistaqt",
        "vtk",
        "vtkmodules",
        "vtkmodules.all",
        "vtkmodules.qt.QVTKRenderWindowInteractor",
        "scipy",
        "scipy.sparse",
        "numpy",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "matplotlib.tests"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PEBDesigner",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # windowed app
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="PEBDesigner",
)
