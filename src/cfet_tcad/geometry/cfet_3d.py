"""3D CFET stack: gate-all-around channel devices stacked vertically.

The pFET device sits at the bottom, the nFET device above it, separated
by the unmeshed common-gate metal (t_gap).  Each channel replica is the
gaa_3d structure — a silicon bar whose gate segment is wrapped by an
oxide shell carrying an all-around gate contact — and a device may hold
several replicas: ``n_fins`` side by side along z at ``fin_pitch``
(paper-style fin arrays) and/or ``n_stacked_sheets`` vertically at
``sheet_pitch`` (multi-nanosheet stacks).  All replicas of a device
share its physical groups (silicon_n / oxide_n / gate_n / si_ox_n, and
_p likewise) — gmsh groups may contain disconnected volumes and DEVSIM
solves a region of disconnected components as a block-diagonal system —
so the naming contract, loader, physics, runner, and renderer all work
unchanged.  The two gate contacts are electrically one common gate
(tied by the runner), with per-device metal workfunctions carried in
MeshLayout.gate_workfunctions.
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
        divisions = [
            [m.nx_sd, m.nx_gate, m.nx_sd],
            [m.ny_ox, m.ny_si, m.ny_ox],
            [m.ny_ox, m.nz_w, m.ny_ox],
        ]
        sheet_height = d.t_si + 2.0 * d.t_ox
        # a device's total height grows with vertically stacked sheets
        device_height = (d.n_stacked_sheets - 1) * d.sheet_pitch \
            + sheet_height
        sheets = [
            ("p", 0.0, d.gate_workfunction_p_ev),
            ("n", device_height + d.t_gap_nm * 1.0e-7,
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

            # geometry for both devices first; the single synchronize comes
            # before any meshing constraint (a later synchronize would
            # silently wipe transfinite settings — see cfet_2d).  Each
            # device holds n_fins x n_stacked_sheets channel replicas
            # (fins along z at fin_pitch, sheets along y at sheet_pitch);
            # all replicas of a device share its physical groups, so the
            # naming contract — and everything downstream — is unchanged.
            built = []
            for suffix, y_base, wf in sheets:
                grids = []
                for fi in range(d.n_fins):
                    z0 = fi * d.fin_pitch
                    zs = [z0 - d.t_ox, z0, z0 + w, z0 + w + d.t_ox]
                    for si in range(d.n_stacked_sheets):
                        y0 = y_base + si * d.sheet_pitch
                        ys = [y0, y0 + d.t_ox, y0 + d.t_ox + d.t_si,
                              y0 + 2.0 * d.t_ox + d.t_si]
                        grids.append(_BlockGrid(xs, ys, zs))
                si_vols = [g.volume(*b) for g in grids
                           for b in silicon_blocks]
                ox_vols = [g.volume(*b) for g in grids
                           for b in oxide_blocks]
                built.append((suffix, wf, grids, si_vols, ox_vols))
            gmsh.model.geo.synchronize()

            for suffix, wf, grids, si_vols, ox_vols in built:
                silicon = f"silicon_{suffix}"
                oxide = f"oxide_{suffix}"
                source, drain = f"source_{suffix}", f"drain_{suffix}"
                gate = f"gate_{suffix}"
                iface = f"si_ox_{suffix}"

                source_faces, drain_faces = [], []
                gate_faces, iface_faces = [], []
                for grid in grids:
                    grid.set_transfinite(divisions)
                    source_faces.append(grid.surface(0, 0, 1, 1))
                    drain_faces.append(grid.surface(0, 3, 1, 1))
                    gate_faces += (
                        [grid.surface(1, 1, 0, k) for k in range(3)] +
                        [grid.surface(1, 1, 3, k) for k in range(3)] +
                        [grid.surface(2, 1, j, 0) for j in range(3)] +
                        [grid.surface(2, 1, j, 3) for j in range(3)])
                    iface_faces += [grid.surface(1, 1, 1, 1),
                                    grid.surface(1, 1, 2, 1),
                                    grid.surface(2, 1, 1, 1),
                                    grid.surface(2, 1, 1, 2)]

                gmsh.model.addPhysicalGroup(3, si_vols, name=silicon)
                gmsh.model.addPhysicalGroup(3, ox_vols, name=oxide)
                gmsh.model.addPhysicalGroup(2, source_faces, name=source)
                gmsh.model.addPhysicalGroup(2, drain_faces, name=drain)
                gmsh.model.addPhysicalGroup(2, gate_faces, name=gate)
                gmsh.model.addPhysicalGroup(2, iface_faces, name=iface)

                layout.regions.update({silicon: "Silicon", oxide: "Oxide"})
                layout.contacts.update({source: silicon, drain: silicon,
                                        gate: oxide})
                layout.interfaces[iface] = (silicon, oxide)
                layout.silicon_polarity[silicon] = suffix
                layout.gate_workfunctions[gate] = wf
                layout.semiconductor_materials[silicon] = (
                    d.channel_material_n if suffix == "n"
                    else d.channel_material_p)
                layout.gate_semiconductors[gate] = silicon

            gmsh.model.mesh.generate(3)
            gmsh.option.setNumber("Mesh.MshFileVersion", 2.2)
            gmsh.write(str(msh_path))
        finally:
            gmsh.finalize()

        return layout
