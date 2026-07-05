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

__version__ = "0.5"
__author__ = "Yu Rui"


def _ensure_devsim_math_libs() -> None:
    """DEVSIM dlopens a BLAS/LAPACK at import time.  On systems where only
    versioned shared objects are installed (e.g. libopenblas.so.0 from the
    Debian/Ubuntu runtime package, without the -dev symlink), DEVSIM's default
    search list fails.  Resolve a usable library and export DEVSIM_MATH_LIBS
    before devsim is imported anywhere in this package."""
    if "DEVSIM_MATH_LIBS" in os.environ:
        return
    for name in ("openblas", "lapack", "blas", "mkl_rt"):
        found = ctypes.util.find_library(name)
        if found:
            os.environ["DEVSIM_MATH_LIBS"] = found
            return


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
