# PyInstaller spec: standalone onedir bundle with two executables sharing
# one runtime folder — cfet-tcad-gui.exe (windowed) and cfet-tcad.exe
# (console CLI; the GUI spawns it for every simulation process).
#
#   pyinstaller packaging/cfet_tcad.spec --noconfirm
#
# devsim and gmsh have no official PyInstaller hooks: both load native
# libraries via ctypes from their package directories, so collect_all
# ships those files intact.  The pip 'mkl' wheel (DEVSIM's BLAS on
# Windows) drops its DLLs into <prefix>/Library/bin, gathered explicitly.

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files

datas, binaries, hiddenimports = [], [], []
for pkg in ("devsim", "gmsh", "pyvista", "pyvistaqt", "vtkmodules"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h
datas += collect_data_files("cfet_tcad")  # bundled help guides + images

if sys.platform == "win32":
    libbin = Path(sys.prefix) / "Library" / "bin"
    if libbin.is_dir():
        binaries += [(str(p), ".") for p in libbin.glob("mkl_*.dll")]
    # the gmsh wheel installs its DLL via the data scheme into
    # <prefix>/lib, outside the package — collect_all misses it; place it
    # both at the bundle root and under lib/ (gmsh.py probes both)
    for dll in (Path(sys.prefix) / "lib").glob("gmsh*.dll"):
        binaries += [(str(dll), "."), (str(dll), "lib")]

common = dict(
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter"],
    noarchive=False,
)

a_gui = Analysis(["entry_gui.py"], **common)
a_cli = Analysis(["entry_cli.py"], **common)

pyz_gui = PYZ(a_gui.pure)
pyz_cli = PYZ(a_cli.pure)

_ICON = str(Path(SPECPATH) / "app.ico")

exe_gui = EXE(
    pyz_gui,
    a_gui.scripts,
    [],
    exclude_binaries=True,
    name="cfet-tcad-gui",
    console=False,
    upx=False,
    icon=_ICON,
)
exe_cli = EXE(
    pyz_cli,
    a_cli.scripts,
    [],
    exclude_binaries=True,
    name="cfet-tcad",
    console=True,
    upx=False,
    icon=_ICON,
)

coll = COLLECT(
    exe_gui,
    exe_cli,
    a_gui.binaries,
    a_gui.zipfiles,
    a_gui.datas,
    a_cli.binaries,
    a_cli.zipfiles,
    a_cli.datas,
    strip=False,
    upx=False,
    name="cfet-tcad",
)
