# -*- mode: python ; coding: utf-8 -*-
import os

from PyInstaller.utils.hooks import collect_all

APP_ICON = os.path.join(SPECPATH, "icon.ico")

datas = [
    ('assets', 'assets'),
    # NOTE: the 'images/' tree is intentionally NOT bundled. The frozen UI loads
    # biome/merchant art from remote URLs and writes runtime screenshots to
    # %CWD%/images at runtime (dirs are created on demand), so bundling those
    # ~8 MB of source images was dead weight.
    ('paths', 'paths'),
    ('config.json', '.'),
    ('maxstellar.png', '.'),
    ('tea.png', '.'),
    ('icon.ico', '.'),
]
# Bundle Tesseract OCR (used by blossom_ocr for merchant auto-buy) when present.
_tess_dir = os.path.join(SPECPATH, 'assets', 'tesseract')
if os.path.isdir(_tess_dir):
    datas.append((_tess_dir, os.path.join('assets', 'tesseract')))

binaries = []
hiddenimports = [
    'webview.platforms.edgechromium',
    'webview.platforms.winforms',
    'blossom_dirs',
    'blossom_prepath',
    'blossom_build_info',
    'blossom_merchant',
    'blossom_ocr',
    'blossom_brsc',
    'blossom_biomes',
    'blossom_buffs',
    'blossom_quests',
    'blossom_ui_scheduler',
    'blossom_macro_session',
    'blossom_license',
    'blossom_biome_selector',
    'blossom_runtime_deps',
    'pytesseract',
    'pyautogui',
    'PIL',
    'PIL.Image',
    'PIL.ImageGrab',
    'keyboard',
    'mouse',
]
tmp_ret = collect_all('webview')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('autoit')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    # Use the real implementation in src/ as the frozen entry point. The root
    # run_local_ui.py is only a dev shim that execs this file by path, which is
    # not bundled into the onefile temp dir and crashes the exe on launch.
    [os.path.join('src', 'run_local_ui.py')],
    pathex=[os.path.join(SPECPATH, 'src')],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # OpenCV (cv2) is an externalized optional dependency: downloaded + hash-
    # verified into %LOCALAPPDATA%\Blossom\runtime on first use of Fishing Mode
    # (see src/blossom_runtime_deps.py). Excluding it here keeps the exe lean.
    # blossom_fishing.py keeps a full NumPy fallback, so the app works even if the
    # bundle is never downloaded. Also drop build-time-only tooling.
    # Only excludes verified unused at runtime via `rg` over src/. NOTE: do not
    # add 'tkinter' (used by calibration_capture.py) or 'setuptools'/'pkg_resources'
    # (imported at load time by some third-party deps) — excluding those crashes
    # the app. cv2 is the intended externalized dependency.
    excludes=[
        'cv2',
        'numpy.f2py',
        'numpy.distutils',
        'numpy.testing',
        'pip',
        'pydoc_data',
    ],
    noarchive=False,
    optimize=0,
)
# Belt-and-suspenders: strip any OpenCV binaries/datas that slipped into the graph.
def _drop_opencv(entries):
    return [e for e in entries if 'cv2' not in e[0].lower() and 'opencv' not in e[0].lower()]

a.binaries = _drop_opencv(a.binaries)
a.datas = _drop_opencv(a.datas)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='BlossomMacro',
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
