from .base import GeometryBuilder, MeshLayout
from .cfet_2d import CFETStack2DBuilder
from .cfet_3d import CFETStack3DBuilder
from .gaa_3d import GAANanosheet3DBuilder
from .nanosheet_2d import Nanosheet2DBuilder
from .params import DeviceParams, MeshParams

#: structure name (DeviceParams.structure) -> builder class
BUILDERS = {
    "nanosheet_2d": Nanosheet2DBuilder,
    "gaa_3d": GAANanosheet3DBuilder,
    "cfet_2d": CFETStack2DBuilder,
    "cfet_3d": CFETStack3DBuilder,
}

__all__ = [
    "DeviceParams",
    "MeshParams",
    "GeometryBuilder",
    "MeshLayout",
    "Nanosheet2DBuilder",
    "GAANanosheet3DBuilder",
    "CFETStack2DBuilder",
    "CFETStack3DBuilder",
    "BUILDERS",
]
