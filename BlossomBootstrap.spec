# -*- mode: python ; coding: utf-8 -*-
import os

APP_ICON = os.path.join(SPECPATH, "icon.ico")
BOOTSTRAP_CHANNEL = os.environ.get("BOOTSTRAP_CHANNEL", "stable").strip().lower()
EXE_NAME = "Blossom-beta" if BOOTSTRAP_CHANNEL == "beta" else "Blossom"

_datas = [
    ("assets/runtime_manifest.json", "assets"),
    ("icon.ico", "."),
]
if os.path.isfile(os.path.join(SPECPATH, "assets", "blossom.png")):
    _datas.append(("assets/blossom.png", "assets"))

datas = _datas

hiddenimports = [
    "blossom_dirs",
    "blossom_runtime_deps",
    "blossom_updater",
    "blossom_build_info",
    "blossom_bootstrap_ui",
    "tkinter",
    "_tkinter",
]

a = Analysis(
    [os.path.join("src", "blossom_bootstrap.py")],
    pathex=[os.path.join(SPECPATH, "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "cv2",
        "webview",
        "PIL",
        "pyautogui",
        "numpy",
        "pip",
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=EXE_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=APP_ICON,
)
