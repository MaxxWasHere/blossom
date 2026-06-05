# -*- mode: python ; coding: utf-8 -*-
# Beta channel build — output dist/BlossomMacro-beta.exe
import glob
import os

from PyInstaller.utils.hooks import collect_all

APP_ICON = os.path.join(SPECPATH, "icon.ico")

datas = [
    ('assets', 'assets'),
    ('images', 'images'),
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
    'pytesseract',
    'pyautogui',
    'PIL',
    'PIL.Image',
    'PIL.ImageGrab',
    'keyboard',
    'mouse',
    'cryptography.hazmat.primitives.asymmetric.ed25519',
]
tmp_ret = collect_all('webview')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('autoit')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
# License + webhooks use requests/cryptography lazily (imported inside functions),
# so PyInstaller's static scan misses them. Bundle explicitly (native backend +
# CA bundle included) so activation, token verification, and webhooks work frozen.
for _pkg in ('requests', 'urllib3', 'certifi', 'charset_normalizer', 'idna', 'cryptography'):
    try:
        _ret = collect_all(_pkg)
        datas += _ret[0]; binaries += _ret[1]; hiddenimports += _ret[2]
    except Exception as _exc:
        print(f"[spec] WARNING: collect_all({_pkg!r}) failed: {_exc}")

# When built with --obfuscate, scripts/build_all.py drops a PyArmor runtime
# package (pyarmor_runtime_XXXXXX) into the project root. Bundle it so the
# obfuscated blossom_license module can load its native runtime at startup.
for _rt in glob.glob(os.path.join(SPECPATH, 'pyarmor_runtime_*')):
    if os.path.isdir(_rt):
        _rt_name = os.path.basename(_rt)
        hiddenimports.append(_rt_name)
        datas.append((_rt, _rt_name))
        print(f"[spec] bundling PyArmor runtime: {_rt_name}")


a = Analysis(
    ['run_local_ui.py'],
    pathex=[os.path.join(SPECPATH, 'src')],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name='BlossomMacro-beta',
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
