"""Abstract geometry builder interface.

Every builder produces a gmsh MSH 2.2 ASCII file whose physical group names
follow the naming contract in :mod:`cfet_tcad.geometry.params` and reports
which groups are regions, contacts, and interfaces so the DEVSIM loader can
consume the mesh without device-specific knowledge.

Phase 2/3 extensions (3D GAA single nanosheet, full CFET stack) plug in as
new subclasses returning their own :class:`MeshLayout`.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

from .params import DeviceParams, MeshParams


@dataclass
class MeshLayout:
    """Describes the physical groups present in a generated mesh file."""

    dimension: int
    #: region name -> DEVSIM material ("Silicon" / "Oxide")
    regions: dict = field(default_factory=dict)
    #: contact name -> region the contact attaches to
    contacts: dict = field(default_factory=dict)
    #: interface name -> (region0, region1)
    interfaces: dict = field(default_factory=dict)


class GeometryBuilder(ABC):
    """Base class for parametric device geometry builders."""

    def __init__(self, device: DeviceParams, mesh: MeshParams | None = None):
        self.device = device
        self.mesh = mesh or MeshParams()

    @abstractmethod
    def build(self, msh_path: Path) -> MeshLayout:
        """Generate the mesh file at ``msh_path`` and return its layout."""
