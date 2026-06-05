# -*- mode: python ; coding: utf-8 -*-
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
]
tmp_ret = collect_all('webview')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('autoit')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


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
