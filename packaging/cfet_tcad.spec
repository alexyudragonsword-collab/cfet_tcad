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

# MKL ships one DLL per threading layer and per vector-math (VML) code
# path, but mkl_rt only ever loads ONE of each at runtime.  Nothing in
# this project sets MKL_THREADING_LAYER, so the default (intel_thread,
# which pulls in libiomp5md at the first BLAS call) is what runs — the
# TBB and sequential layers are never reached.  VML is Intel's vector
# math library (vdExp/vdMul/…); DEVSIM calls BLAS/LAPACK and the sparse
# solvers, and numpy/scipy on PyPI link OpenBLAS rather than MKL, so no
# VML entry point is ever called.  Together that is ~123 MB of dead
# weight.  The CPU-dispatch variants (def/mc3/avx2/avx512/avx10) all
# STAY: mkl_rt picks one from the host CPU at load time, so dropping any
# of them breaks precisely the machines that need it.
_MKL_SKIP_PREFIXES = ("mkl_tbb_thread", "mkl_sequential", "mkl_vml_")

if sys.platform == "win32":
    libbin = Path(sys.prefix) / "Library" / "bin"
    if libbin.is_dir():
        for pattern in ("mkl_*.dll", "libiomp5md*.dll"):
            for p in libbin.glob(pattern):
                if p.name.startswith(_MKL_SKIP_PREFIXES):
                    continue
                binaries += [(str(p), ".")]
        # the dispatcher and the one threading layer we rely on are not
        # optional — fail the build loudly rather than ship a bundle that
        # only dies on the first solve
        _names = {Path(src).name for src, _ in binaries}
        for _required in ("mkl_rt", "mkl_core", "mkl_intel_thread", "libiomp5md"):
            assert any(n.startswith(_required) for n in _names), f"{_required} missing"
    # the gmsh wheel installs its DLL via the data scheme into
    # <prefix>/lib, outside the package — collect_all misses it.  gmsh.py
    # probes `os.path.dirname(__file__)` FIRST (see its possible_libpaths),
    # and that resolves to the bundle root here, so the root copy is the
    # one that loads; a second copy under lib/ was never reached (~86 MB).
    _gmsh_dlls = list((Path(sys.prefix) / "lib").glob("gmsh*.dll"))
    assert _gmsh_dlls, "gmsh DLL not found under <prefix>/lib"
    for dll in _gmsh_dlls:
        binaries += [(str(dll), ".")]

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
