"""Load a gmsh mesh (MSH 2.2) into DEVSIM using a :class:`MeshLayout`."""

from pathlib import Path

import devsim

from ..geometry.base import MeshLayout


def load_mesh(msh_path: Path, layout: MeshLayout, device: str,
              mesh_name: str | None = None) -> str:
    """Create a DEVSIM device from a gmsh mesh file.

    Region/contact/interface physical-group names in the file must match the
    layout (the geometry builders guarantee this by contract).  Returns the
    device name.
    """
    mesh_name = mesh_name or f"{device}_mesh"
    devsim.create_gmsh_mesh(mesh=mesh_name, file=str(msh_path))

    for region, material in layout.regions.items():
        devsim.add_gmsh_region(mesh=mesh_name, gmsh_name=region,
                               region=region, material=material)
    for contact, region in layout.contacts.items():
        devsim.add_gmsh_contact(mesh=mesh_name, gmsh_name=contact,
                                region=region, name=contact, material="metal")
    for interface, (r0, r1) in layout.interfaces.items():
        devsim.add_gmsh_interface(mesh=mesh_name, gmsh_name=interface,
                                  name=interface, region0=r0, region1=r1)

    devsim.finalize_mesh(mesh=mesh_name)
    devsim.create_device(mesh=mesh_name, device=device)
    return device
