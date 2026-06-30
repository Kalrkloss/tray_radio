# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = ['PyQt5.QtCore', 'PyQt5.QtWidgets', 'PyQt5.QtGui', 'pystray._win32', 'pystray._util.win32', 'win32com', 'win32com.propsys', 'win32com.shell', 'pythoncom', 'av.codec_context', 'av.audio_resampler', 'av.container', 'av.stream', 'av.format', 'av.codec', 'av.utils', 'pypac', 'pypac.pac_parser', 'numpy', 'PIL.Image', 'PIL.ImageDraw', 'requests', 'miniaudio']
tmp_ret = collect_all('av')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('miniaudio')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['C:\\Users\\HERMANE\\git\\tray_radio\\main.py'],
    pathex=[],
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
    name='Tray Radio',
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
    icon=['C:\\Users\\HERMANE\\git\\tray_radio\\dist\\tray_radio.ico'],
)
