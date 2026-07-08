"""cfet_tcad: open-source CFET / nanosheet TCAD simulation system.

Component mapping against the Synopsys Sentaurus tool chain:

=====================  =========================================
Sentaurus              cfet_tcad
=====================  =========================================
Structure Editor       cfet_tcad.geometry (gmsh parametric build)
Sentaurus Device       cfet_tcad.physics + cfet_tcad.solve (DEVSIM)
Sentaurus Visual       cfet_tcad.io (VTK output for VisIt)
Workbench              cfet_tcad.workflow (YAML-driven runner)
Inspect                cfet_tcad.extract (Vt/SS/DIBL/Ion/Ioff)
=====================  =========================================
"""

import ctypes.util
import os
import sys
from pathlib import Path

__version__ = "0.5.2"
__author__ = "Yu Rui"
__app_name__ = "STACKED CMOS TCAD"
__copyright__ = "Copyright © 2026 Yu Rui"
__license__ = "Apache-2.0"

_IS_WINDOWS = os.name == "nt"


def _ensure_std_streams() -> None:
    """Windowed frozen apps (cfet-tcad-gui.exe double-clicked from
    Explorer) have no console: PyInstaller leaves sys.stdout/stderr as
    None, and DEVSIM's import-time prints then raise inside the
    extension's init ("initialization of devsim_py3 raised unreported
    exception").  Launching the same exe from a terminal inherits valid
    handles, which is why CI smokes pass while double-click fails - so
    give headless processes a sink before anything prints."""
    if not getattr(sys, "frozen", False):
        return
    for name in ("stdout", "stderr"):
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))


_ensure_std_streams()

# BLAS/LAPACK DLL patterns DEVSIM can use, in preference order
_WIN_BLAS_GLOBS = ("mkl_rt*.dll", "libopenblas*.dll")
_UNIX_BLAS_NAMES = ("openblas", "lapack", "blas", "mkl_rt")


def _add_dll_dir(directory: Path) -> None:
    """Make a directory visible to both Windows DLL loaders (DEVSIM loads
    through plain LoadLibrary, which honors PATH but not
    os.add_dll_directory alone)."""
    os.add_dll_directory(str(directory))
    os.environ["PATH"] = f"{directory}{os.pathsep}" + os.environ.get("PATH", "")


def _preload(dll: Path) -> None:
    """Load the BLAS DLL into the process by full Unicode path before
    DEVSIM asks for it.  DEVSIM's own narrow-string LoadLibrary then
    resolves the already-loaded module by basename without touching the
    filesystem - immune to non-ASCII install paths, deep paths beyond
    MAX_PATH, and codepage quirks.  A failure here is only a warning:
    DEVSIM still gets its own chance through the PATH search."""
    try:
        import ctypes
        ctypes.WinDLL(str(dll))
    except OSError as exc:  # pragma: no cover - Windows-only branch
        print(f"warning: could not preload {dll.name}: {exc}",
              file=sys.stderr)


def _find_math_library() -> str | None:
    # NB (Windows): return the bare DLL *filename* and register its
    # directory with the loaders instead of passing a full path.  DEVSIM's
    # C++ side reads DEVSIM_MATH_LIBS as a narrow string, so a full path
    # containing non-ASCII characters (e.g. an install dir under a Chinese
    # user name) fails to load; a plain ASCII filename resolved through
    # the Unicode-aware PATH search works from any install location.
    if getattr(sys, "frozen", False):
        # PyInstaller onedir: DLLs live next to the exe or in _internal
        exe_dir = Path(sys.executable).parent
        for d in (exe_dir, exe_dir / "_internal"):
            if not d.is_dir():
                continue
            patterns = (_WIN_BLAS_GLOBS if _IS_WINDOWS
                        else ("libopenblas.so*", "liblapack.so*"))
            for pattern in patterns:
                hits = sorted(d.glob(pattern))
                if hits:
                    if _IS_WINDOWS:
                        _add_dll_dir(d)
                        _preload(hits[0])
                        return hits[0].name
                    return str(hits[0])
        return None
    if _IS_WINDOWS:
        # the pip 'mkl' wheel drops its DLLs into <prefix>/Library/bin
        libbin = Path(sys.prefix) / "Library" / "bin"
        if libbin.is_dir():
            for pattern in _WIN_BLAS_GLOBS:
                hits = sorted(libbin.glob(pattern))
                if hits:
                    _add_dll_dir(libbin)
                    _preload(hits[0])
                    return hits[0].name
        return ctypes.util.find_library("mkl_rt")
    for name in _UNIX_BLAS_NAMES:
        found = ctypes.util.find_library(name)
        if found:
            return found
    return None


def _ensure_devsim_math_libs() -> None:
    """DEVSIM dlopens a BLAS/LAPACK at import time; its default search list
    misses versioned Linux sonames (libopenblas.so.0 without the -dev
    symlink), the pip MKL location on Windows, and PyInstaller layouts.
    Resolve a usable library and export DEVSIM_MATH_LIBS before devsim is
    imported anywhere in this package."""
    if "DEVSIM_MATH_LIBS" in os.environ:
        return
    library = _find_math_library()
    if library:
        os.environ["DEVSIM_MATH_LIBS"] = library


_ensure_devsim_math_libs()


def reset() -> None:
    """Clear all DEVSIM state (meshes, devices, models, parameters).

    ``devsim.reset_devsim()`` also wipes the ``direct_solver`` parameter
    that devsim configures at import time, so restore the UMFPACK shim —
    without it the next solve fails with 'Unrecognized direct_solver'.
    """
    import devsim
    from devsim.umfpack import umfshim

    devsim.reset_devsim()
    devsim.set_parameter(name="direct_solver", value="custom")
    devsim.set_parameter(name="solver_callback",
                         value=umfshim.local_solver_callback)
