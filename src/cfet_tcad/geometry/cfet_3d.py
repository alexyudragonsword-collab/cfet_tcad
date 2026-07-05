"""3D CFET stack: two gate-all-around nanosheets stacked vertically.

The pFET sheet sits at the bottom, the nFET sheet above it, separated by
the unmeshed common-gate metal (t_gap).  Each sheet is the gaa_3d
structure — a silicon bar whose gate segment is wrapped by an oxide shell
carrying a single all-around gate contact — with per-sheet names
(silicon_n / oxide_n / gate_n / si_ox_n, and _p likewise).  The two gate
contacts are electrically one common gate (tied by the runner), with
per-sheet metal workfunctions carried in MeshLayout.gate_workfunctions.

Both CFET experiments (cfet_idvg, cfet_vtc) run on this structure
unchanged: the runner derives gates, drains, polarities, and current
scaling from the MeshLayout contract.
"""

from pathlib import Path

import gmsh

from .base import GeometryBuilder, MeshLayout
from .gaa_3d import _BlockGrid


class CFETStack3DBuilder(GeometryBuilder):
    """Stacked nFET-on-pFET gate-all-around nanosheets in full 3D."""

    def build(self, msh_path: Path) -> MeshLayout:
        d, m = self.device, self.mesh
        msh_path = Path(msh_path)
        msh_path.parent.mkdir(parents=True, exist_ok=True)

        w = d.sheet_width_nm * 1.0e-7  # cm
        xs = [0.0, d.l_sd, d.l_sd + d.l_gate, d.l_total]
        zs = [-d.t_ox, 0.0, w, w + d.t_ox]
        divisions = [
            [m.nx_sd, m.nx_gate, m.nx_sd],
            [m.ny_ox, m.ny_si, m.ny_ox],
            [m.ny_ox, m.nz_w, m.ny_ox],
        ]
        sheet_height = d.t_si + 2.0 * d.t_ox
        sheets = [
            ("p", 0.0, d.gate_workfunction_p_ev),
            ("n", sheet_height + d.t_gap_nm * 1.0e-7,
             d.gate_workfunction_n_ev),
        ]

        silicon_blocks = [(i, 1, 1) for i in range(3)]
        oxide_blocks = [(1, j, k) for j in range(3) for k in range(3)
                        if (j, k) != (1, 1)]

        layout = MeshLayout(dimension=3)
        gmsh.initialize()
        try:
            gmsh.option.setNumber("General.Terminal", 0)
            gmsh.model.add("cfet3d")

            # geometry for both sheets first; the single synchronize comes
            # before any meshing constraint (a later synchronize would
            # silently wipe transfinite settings — see cfet_2d)
            built = []
            for suffix, y0, wf in sheets:
                ys = [y0, y0 + d.t_ox, y0 + d.t_ox + d.t_si,
                      y0 + 2.0 * d.t_ox + d.t_si]
                grid = _BlockGrid(xs, ys, zs)
                si_vols = [grid.volume(*b) for b in silicon_blocks]
                ox_vols = [grid.volume(*b) for b in oxide_blocks]
                built.append((suffix, wf, grid, si_vols, ox_vols))
            gmsh.model.geo.synchronize()

            for suffix, wf, grid, si_vols, ox_vols in built:
                grid.set_transfinite(divisions)

                silicon = f"silicon_{suffix}"
                oxide = f"oxide_{suffix}"
                source, drain = f"source_{suffix}", f"drain_{suffix}"
                gate = f"gate_{suffix}"
                iface = f"si_ox_{suffix}"

                gmsh.model.addPhysicalGroup(3, si_vols, name=silicon)
                gmsh.model.addPhysicalGroup(3, ox_vols, name=oxide)
                gmsh.model.addPhysicalGroup(2, [grid.surface(0, 0, 1, 1)],
                                            name=source)
                gmsh.model.addPhysicalGroup(2, [grid.surface(0, 3, 1, 1)],
                                            name=drain)
                gate_faces = (
                    [grid.surface(1, 1, 0, k) for k in range(3)] +
                    [grid.surface(1, 1, 3, k) for k in range(3)] +
                    [grid.surface(2, 1, j, 0) for j in range(3)] +
                    [grid.surface(2, 1, j, 3) for j in range(3)])
                gmsh.model.addPhysicalGroup(2, gate_faces, name=gate)
                iface_faces = [grid.surface(1, 1, 1, 1),
                               grid.surface(1, 1, 2, 1),
                               grid.surface(2, 1, 1, 1),
                               grid.surface(2, 1, 1, 2)]
                gmsh.model.addPhysicalGroup(2, iface_faces, name=iface)

                layout.regions.update({silicon: "Silicon", oxide: "Oxide"})
                layout.contacts.update({source: silicon, drain: silicon,
                                        gate: oxide})
                layout.interfaces[iface] = (silicon, oxide)
                layout.silicon_polarity[silicon] = suffix
                layout.gate_workfunctions[gate] = wf

            gmsh.model.mesh.generate(3)
            gmsh.option.setNumber("Mesh.MshFileVersion", 2.2)
            gmsh.write(str(msh_path))
        finally:
            gmsh.finalize()

        return layout
