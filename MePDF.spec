# -*- mode: python ; coding: utf-8 -*-
"""Cross-platform PyInstaller specification for MePDF (Windows & macOS)."""

import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

ROOT_DIR = Path(SPECPATH).resolve()

datas = [
    (str(ROOT_DIR / "assets"), "assets"),
    (str(ROOT_DIR / "LICENSE"), "."),
]
binaries = []
hiddenimports = [
    "pymupdf",
    "fitz",
    "pikepdf",
    "pikepdf._core",
    "PIL",
]

for pkg in ("pymupdf", "pikepdf"):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

excludes = [
    "pytest",
    "pytest_qt",
    "tkinter",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtQuick",
    "PySide6.QtQuickWidgets",
    "PySide6.QtQml",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DRender",
    "PySide6.QtMultimedia",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
]

win_icon = str(ROOT_DIR / "assets" / "mepdf.ico")
mac_icon = str(ROOT_DIR / "assets" / "mepdf.icns")
app_icon = win_icon if sys.platform == "win32" else (mac_icon if sys.platform == "darwin" else None)

a = Analysis(
    [str(ROOT_DIR / "main.py")],
    pathex=[str(ROOT_DIR)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MePDF",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=app_icon,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="MePDF",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="MePDF.app",
        icon=mac_icon,
        bundle_identifier="io.github.msiahaan.mepdf",
        info_plist={
            "CFBundleName": "MePDF",
            "CFBundleDisplayName": "MePDF",
            "CFBundleShortVersionString": "1.0.0",
            "CFBundleVersion": "1.0.0",
            "NSHighResolutionCapable": True,
            "NSPrincipalClass": "NSApplication",
            "LSMinimumSystemVersion": "11.0",
            "CFBundleDocumentTypes": [
                {
                    "CFBundleTypeName": "PDF Document",
                    "CFBundleTypeRole": "Editor",
                    "LSHandlerRank": "Alternate",
                    "CFBundleTypeExtensions": ["pdf", "PDF"],
                    "CFBundleTypeMIMETypes": ["application/pdf"],
                    "LSItemContentTypes": ["com.adobe.pdf"],
                }
            ],
        },
    )
