"""Environment self-diagnosis: ``cfet-tcad doctor``.

Prints a copy-pasteable report of everything the runtime bootstrap
depends on, then walks the load chain step by step (BLAS DLL -> devsim
import -> gmsh import -> tiny solve), so a broken install pinpoints its
first failing link instead of dying in devsim's opaque
"initialization raised unreported exception".
"""

import locale
import os
import platform
import sys
import traceback
from pathlib import Path


def _section(title: str) -> None:
    print(f"\n=== {title} ===")


def _try(label: str, fn) -> bool:
    try:
        result = fn()
        print(f"[ OK ] {label}" + (f": {result}" if result else ""))
        return True
    except Exception:  # noqa: BLE001 - report everything, keep walking
        print(f"[FAIL] {label}")
        traceback.print_exc()
        return False


def run_doctor() -> int:
    import cfet_tcad

    _section("environment")
    print("app version :", cfet_tcad.__version__)
    print("python      :", sys.version)
    print("platform    :", platform.platform())
    print("machine     :", platform.machine())
    print("frozen      :", getattr(sys, "frozen", False))
    print("executable  :", sys.executable)
    print("cwd         :", os.getcwd())
    print("locale      :", locale.getlocale(), "|",
          locale.getpreferredencoding(False))
    print("fs encoding :", sys.getfilesystemencoding())

    _section("bootstrap state")
    print("DEVSIM_MATH_LIBS :", os.environ.get("DEVSIM_MATH_LIBS"))
    for entry in os.environ.get("PATH", "").split(os.pathsep)[:3]:
        print("PATH[..]         :", entry)

    exe_dir = Path(sys.executable).parent
    _section("bundle contents")
    for d in (exe_dir, exe_dir / "_internal"):
        if not d.is_dir():
            continue
        for pattern in ("mkl_rt*.dll", "libiomp5md*.dll", "gmsh*.dll",
                        "libopenblas*"):
            for hit in sorted(d.glob(pattern)):
                print(f"found: {hit}  ({hit.stat().st_size} bytes)")
    print("configs dir      :", (exe_dir / "configs").is_dir())

    ok = True
    _section("load chain")
    if cfet_tcad._IS_WINDOWS:
        name = os.environ.get("DEVSIM_MATH_LIBS", "").split(";")[0]
        if name:
            def load_blas():
                import ctypes
                ctypes.WinDLL(name)  # resolves like DEVSIM will
                return name
            ok &= _try("load BLAS DLL by name", load_blas)

    def import_devsim():
        import devsim
        return f"devsim {getattr(devsim, '__version__', '?')}"
    ok &= _try("import devsim (drift-diffusion solver)", import_devsim)

    def import_gmsh():
        import gmsh
        return "gmsh module loads"
    ok &= _try("import gmsh (meshing)", import_gmsh)

    def solve():
        from ..geometry import BUILDERS, DeviceParams, MeshParams
        from ..meshio_devsim import load_mesh
        from ..solve import setup_equilibrium
        import tempfile
        dev = DeviceParams(name="doctor", structure="nanosheet_2d")
        mesh = MeshParams(nx_sd=4, nx_gate=6, ny_si=3, ny_ox=2)
        with tempfile.TemporaryDirectory() as tmp:
            msh = Path(tmp) / "doctor.msh"
            layout = BUILDERS["nanosheet_2d"](dev, mesh).build(msh)
            load_mesh(msh, layout, "doctor")
            setup_equilibrium("doctor", layout, dev)
        return "equilibrium solved (mesh+doping+BLAS+UMFPACK all live)"
    ok &= _try("tiny end-to-end solve", solve)

    _section("verdict")
    print("all checks passed - the runtime is healthy" if ok else
          "first [FAIL] above is the broken link - please report "
          "this full output")
    return 0 if ok else 1
