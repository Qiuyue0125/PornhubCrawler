# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all


selenium_datas, selenium_binaries, selenium_hiddenimports = collect_all('selenium')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=selenium_binaries,
    datas=[('../Bin', 'Bin'), ('config.json', 'Bin')] + selenium_datas,
    hiddenimports=selenium_hiddenimports,
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
    [],
    exclude_binaries=True,
    name='ph_crawler',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='../Bin/ico.ico',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ph_crawler',
)
