import os
import sys
import subprocess

sys.path.insert(0, os.path.dirname(__file__))

from icon_generator import create_playing_icon

DIST_DIR = os.path.join(os.path.dirname(__file__), "dist")
ICO_PATH = os.path.join(DIST_DIR, "tray_radio.ico")

os.makedirs(DIST_DIR, exist_ok=True)

ico = create_playing_icon()
ico.save(ICO_PATH, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
print(f"Icon saved to {ICO_PATH}")

args = [
    sys.executable, "-m", "PyInstaller",
    "--onefile",
    "--noconsole",
    "--name", "Tray Radio",
    "--distpath", DIST_DIR,
    "--icon", ICO_PATH,
    "--hidden-import", "PyQt5.QtCore",
    "--hidden-import", "PyQt5.QtWidgets",
    "--hidden-import", "PyQt5.QtGui",
    "--hidden-import", "pystray._win32",
    "--hidden-import", "pystray._util.win32",
    "--hidden-import", "win32com",
    "--hidden-import", "win32com.propsys",
    "--hidden-import", "win32com.shell",
    "--hidden-import", "pythoncom",
    "--hidden-import", "av.codec_context",
    "--hidden-import", "av.audio_resampler",
    "--hidden-import", "av.container",
    "--hidden-import", "av.stream",
    "--hidden-import", "av.format",
    "--hidden-import", "av.codec",
    "--hidden-import", "av.utils",
    "--hidden-import", "pypac",
    "--hidden-import", "pypac.pac_parser",
    "--hidden-import", "numpy",
    "--hidden-import", "PIL.Image",
    "--hidden-import", "PIL.ImageDraw",
    "--hidden-import", "requests",
    "--hidden-import", "miniaudio",
    "--collect-all", "av",
    "--collect-all", "miniaudio",
    os.path.join(os.path.dirname(__file__), "main.py"),
]

print("Running PyInstaller...")
print(" ".join(args))
subprocess.run(args, check=True)
print(f"\nDone! Executable in: {os.path.join(DIST_DIR, 'Tray Radio.exe')}")

# Step 2: Build MSI with WiX
MSI_SRC = os.path.join(os.path.dirname(__file__), "installer.wxs")
MSI_OUT = os.path.join(DIST_DIR, "Tray Radio.msi")

if os.path.exists(MSI_SRC):
    print("\nBuilding MSI with WiX...")
    wix_args = [
        "wix", "build",
        MSI_SRC,
        "-o", MSI_OUT,
        "-arch", "x64",
        "-acceptEula", "wix7",
    ]
    print(" ".join(wix_args))
    subprocess.run(wix_args, check=True)
    print(f"\nDone! MSI in: {MSI_OUT}")
else:
    print(f"\nSkipping MSI: {MSI_SRC} not found")
