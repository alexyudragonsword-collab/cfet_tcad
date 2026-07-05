"""VTK export for VisIt / ParaView.

DEVSIM's ``write_devices(type="vtk")`` writes one ``.vtu`` per region plus a
``.pvd`` collection for a single state.  For bias sweeps we write one
snapshot per selected bias point and generate a master ``.pvd`` whose
timesteps are the sweep bias values, so VisIt/ParaView can animate the sweep
directly.
"""

import xml.etree.ElementTree as ET
from pathlib import Path

import devsim


def write_snapshot(prefix: Path) -> list[Path]:
    """Write the current device state; returns the .vtu files produced."""
    prefix = Path(prefix)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    devsim.write_devices(file=str(prefix), type="vtk")
    return sorted(prefix.parent.glob(f"{prefix.name}*.vtu"))


def write_sweep_collection(pvd_path: Path,
                           snapshots: list[tuple[float, list[Path]]]) -> Path:
    """Write a ParaView/VisIt .pvd collection.

    ``snapshots``: list of (bias_value, vtu_files) pairs; the bias value is
    used as the timestep and each region's .vtu becomes a part.
    """
    pvd_path = Path(pvd_path)
    root = ET.Element("VTKFile", type="Collection", version="0.1",
                      byte_order="LittleEndian")
    coll = ET.SubElement(root, "Collection")
    for bias, files in snapshots:
        for part, vtu in enumerate(files):
            ET.SubElement(coll, "DataSet", timestep=f"{bias:.6g}",
                          part=str(part), file=vtu.name)
    tree = ET.ElementTree(root)
    ET.indent(tree)
    tree.write(pvd_path, xml_declaration=True, encoding="utf-8")
    return pvd_path
