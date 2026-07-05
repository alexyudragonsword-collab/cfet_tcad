"""Design import: consume a user-supplied gmsh mesh instead of building one.

``device.structure: external`` selects this pseudo-builder.  The user
provides an MSH 2.2 ASCII file plus the physical-group mapping the DEVSIM
loader needs (the parametric builders derive the same information from
their naming contract):

.. code-block:: yaml

    device:
      structure: external
      external:
        mesh_file: my_device.msh   # relative paths resolve against the
        dimension: 2               #   config file's directory
        regions: {bulk: Silicon, gox: Oxide}
        contacts: {source: bulk, drain: bulk, gate: gox}
        interfaces: {si_ox: [bulk, gox]}
        silicon_polarity: {bulk: n}          # optional
        gate_workfunctions: {gate: 4.5}      # optional
        semiconductor_materials: {bulk: SiGe30}  # optional
        gate_semiconductors: {gate: bulk}    # optional
        doping:                              # optional, default lateral_sd
          bulk: {profile: uniform, donors_cm3: 1.0e17, acceptors_cm3: 0}

Physical correctness of the mesh (junction placement vs. the chosen
doping profile, contact placement, unit system = cm) is the user's
responsibility.
"""

import shutil
from pathlib import Path

from .base import GeometryBuilder, MeshLayout


def read_msh_physical_names(msh_path: Path) -> list[str]:
    """Physical group names declared in an MSH 2.2 ASCII file.

    Raises a ValueError with a conversion hint for other MSH versions
    (DEVSIM's gmsh reader only understands the 2.2 ASCII format).
    """
    msh_path = Path(msh_path)
    names: list[str] = []
    with open(msh_path, encoding="utf-8", errors="replace") as f:
        section = None
        expect_count = False
        for line in f:
            line = line.strip()
            if line.startswith("$End"):
                section = None
                continue
            if line.startswith("$"):
                section = line[1:]
                expect_count = True
                continue
            if section == "MeshFormat":
                version = line.split()[0]
                if not version.startswith("2.2"):
                    raise ValueError(
                        f"{msh_path.name} is MSH format {version}; DEVSIM "
                        f"needs MSH 2.2 ASCII - convert with: "
                        f"gmsh {msh_path.name} -save_all -format msh2 "
                        f"-o converted.msh")
                section = None
            elif section == "PhysicalNames":
                if expect_count:  # first line of the section is the count
                    expect_count = False
                    continue
                # <dimension> <tag> "<name>"
                parts = line.split(None, 2)
                if len(parts) == 3:
                    names.append(parts[2].strip().strip('"'))
    return names


class ExternalMeshBuilder(GeometryBuilder):
    """Pseudo-builder: validates and stages the user's mesh file."""

    def build(self, msh_path: Path) -> MeshLayout:
        ext = self.device.external  # validated by DeviceParams
        src = Path(ext["mesh_file"])
        if not src.exists():
            raise FileNotFoundError(f"external mesh not found: {src}")

        available = read_msh_physical_names(src)
        wanted = (list(ext["regions"]) + list(ext["contacts"])
                  + list(ext.get("interfaces") or {}))
        missing = [n for n in wanted if n not in available]
        if missing:
            raise ValueError(
                f"physical group(s) {missing} not in {src.name}; "
                f"available groups: {sorted(available)}")

        # stage into the run's output directory so results stay
        # self-contained (same contract as the parametric builders)
        msh_path = Path(msh_path)
        msh_path.parent.mkdir(parents=True, exist_ok=True)
        if src.resolve() != msh_path.resolve():
            shutil.copyfile(src, msh_path)

        return MeshLayout(
            dimension=int(ext["dimension"]),
            regions=dict(ext["regions"]),
            contacts=dict(ext["contacts"]),
            interfaces={k: tuple(v) for k, v in
                        (ext.get("interfaces") or {}).items()},
            silicon_polarity=dict(ext.get("silicon_polarity") or {}),
            gate_workfunctions=dict(ext.get("gate_workfunctions") or {}),
            semiconductor_materials=dict(
                ext.get("semiconductor_materials") or {}),
            gate_semiconductors=dict(ext.get("gate_semiconductors") or {}),
            doping_specs=dict(ext.get("doping") or {}),
        )
