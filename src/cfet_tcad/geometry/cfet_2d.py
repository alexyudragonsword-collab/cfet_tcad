"""2D CFET stack: nFET nanosheet stacked over a pFET nanosheet.

Vertical structure (y, bottom to top; units = cm):

    gate_top      (contact)
    oxide_n_top
    silicon_n     nFET sheet   <- source_n / drain_n at the x ends
    oxide_n_bottom
    gate_mid_n    (contact)
    == t_gap: common-gate metal, unmeshed ==
    gate_mid_p    (contact)
    oxide_p_top
    silicon_p     pFET sheet   <- source_p / drain_p at the x ends
    oxide_p_bottom
    gate_bottom   (contact)

All four gate contacts are electrically one common gate (the runner ties
their biases); n and p devices may use different gate metals (per-sheet
workfunctions carried in MeshLayout.gate_workfunctions).  The two sheets
are geometrically disconnected meshes inside one DEVSIM device — the gate
metal between them screens the devices from each other, which is exactly
what terminating both domains on gate contacts models — and are solved in
a single coupled Newton system.

Each sheet reuses the double-gate pattern of nanosheet_2d (3x3 transfinite
block grid, structured triangles, MSH 2.2 ASCII).
"""

from pathlib import Path

import gmsh

from .base import GeometryBuilder, MeshLayout


class CFETStack2DBuilder(GeometryBuilder):
    """Stacked nFET-on-pFET double-gate cross section."""

    def build(self, msh_path: Path) -> MeshLayout:
        d, m = self.device, self.mesh
        msh_path = Path(msh_path)
        msh_path.parent.mkdir(parents=True, exist_ok=True)

        xs = [0.0, d.l_sd, d.l_sd + d.l_gate, d.l_total]
        nx = [m.nx_sd, m.nx_gate, m.nx_sd]
        sheet_height = d.t_si + 2.0 * d.t_ox
        # (suffix, y offset, lower gate contact, upper gate contact)
        sheets = [
            ("p", 0.0, "gate_bottom", "gate_mid_p"),
            ("n", sheet_height + d.t_gap_nm * 1.0e-7, "gate_mid_n",
             "gate_top"),
        ]

        layout = MeshLayout(dimension=2)
        gmsh.initialize()
        try:
            gmsh.option.setNumber("General.Terminal", 0)
            gmsh.model.add("cfet2d")
            geo = gmsh.model.geo

            # build all geometry first: a geo.synchronize() wipes meshing
            # constraints set earlier, so transfinite setup must come after
            # the one and only synchronize
            built = []
            for suffix, y0, gate_lo, gate_hi in sheets:
                ys = [y0, y0 + d.t_ox, y0 + d.t_ox + d.t_si,
                      y0 + 2.0 * d.t_ox + d.t_si]
                pts = [[geo.addPoint(x, y, 0.0) for y in ys] for x in xs]
                h = [[geo.addLine(pts[i][j], pts[i + 1][j]) for j in range(4)]
                     for i in range(3)]
                v = [[geo.addLine(pts[i][j], pts[i][j + 1]) for j in range(3)]
                     for i in range(4)]
                s = [[None] * 3 for _ in range(3)]
                for i in range(3):
                    for j in range(3):
                        loop = geo.addCurveLoop(
                            [h[i][j], v[i + 1][j], -h[i][j + 1], -v[i][j]])
                        s[i][j] = geo.addPlaneSurface([loop])
                built.append((suffix, gate_lo, gate_hi, h, v, s))
            geo.synchronize()

            ny = [m.ny_ox, m.ny_si, m.ny_ox]
            for suffix, gate_lo, gate_hi, h, v, s in built:
                for i in range(3):
                    for j in range(4):
                        gmsh.model.mesh.setTransfiniteCurve(h[i][j], nx[i] + 1)
                for i in range(4):
                    for j in range(3):
                        if j == 1:
                            gmsh.model.mesh.setTransfiniteCurve(
                                v[i][j], ny[j] + 1, "Bump", m.si_bump)
                        else:
                            gmsh.model.mesh.setTransfiniteCurve(
                                v[i][j], ny[j] + 1)
                for i in range(3):
                    for j in range(3):
                        gmsh.model.mesh.setTransfiniteSurface(s[i][j])

                silicon = f"silicon_{suffix}"
                ox_bot = f"oxide_{suffix}_bottom"
                ox_top = f"oxide_{suffix}_top"
                source, drain = f"source_{suffix}", f"drain_{suffix}"
                if_bot = f"si_ox_{suffix}_bottom"
                if_top = f"si_ox_{suffix}_top"

                gmsh.model.addPhysicalGroup(
                    2, [s[i][0] for i in range(3)], name=ox_bot)
                gmsh.model.addPhysicalGroup(
                    2, [s[i][1] for i in range(3)], name=silicon)
                gmsh.model.addPhysicalGroup(
                    2, [s[i][2] for i in range(3)], name=ox_top)
                gmsh.model.addPhysicalGroup(1, [v[0][1]], name=source)
                gmsh.model.addPhysicalGroup(1, [v[3][1]], name=drain)
                gmsh.model.addPhysicalGroup(1, [h[1][0]], name=gate_lo)
                gmsh.model.addPhysicalGroup(1, [h[1][3]], name=gate_hi)
                gmsh.model.addPhysicalGroup(
                    1, [h[i][1] for i in range(3)], name=if_bot)
                gmsh.model.addPhysicalGroup(
                    1, [h[i][2] for i in range(3)], name=if_top)

                wf = (d.gate_workfunction_n_ev if suffix == "n"
                      else d.gate_workfunction_p_ev)
                layout.regions.update({silicon: "Silicon",
                                       ox_bot: "Oxide", ox_top: "Oxide"})
                layout.contacts.update({source: silicon, drain: silicon,
                                        gate_lo: ox_bot, gate_hi: ox_top})
                layout.interfaces.update({if_bot: (silicon, ox_bot),
                                          if_top: (silicon, ox_top)})
                layout.silicon_polarity[silicon] = suffix
                layout.gate_workfunctions.update({gate_lo: wf, gate_hi: wf})

            gmsh.model.mesh.generate(2)
            gmsh.option.setNumber("Mesh.MshFileVersion", 2.2)
            gmsh.write(str(msh_path))
        finally:
            gmsh.finalize()

        return layout
