"""2D double-gate nanosheet cross section built with the gmsh Python API.

Layout (x = transport direction, y = confinement direction, units = cm):

        y
        ^   x=0      x1=L_sd     x2=L_sd+L_g      x3=L_total
  y3 ---+   +---------+--GATE_TOP--+---------+
        |   |             oxide_top            |
  y2 ---+   +---------+------------+----------+   <- si_ox_top
        |   | source  |  channel   |  drain   |   (single silicon region,
  y1 ---+   +---------+------------+----------+    doping set analytically)
        |   |            oxide_bottom          |
  y0 ---+   +---------+-GATE_BOTTOM-+---------+

Source/drain contacts sit on the left/right silicon edges; the two gate
contacts cover only the gate length on the outer oxide boundaries.  The mesh
is transfinite (structured triangles) with a bump grading that concentrates
silicon nodes at the oxide interfaces.  Output is MSH 2.2 ASCII, the only
gmsh format DEVSIM reads.
"""

from pathlib import Path

import gmsh

from .base import GeometryBuilder, MeshLayout
from .params import (
    CONTACT_DRAIN,
    CONTACT_GATE_BOTTOM,
    CONTACT_GATE_TOP,
    CONTACT_SOURCE,
    INTERFACE_SI_OX_BOTTOM,
    INTERFACE_SI_OX_TOP,
    REGION_OXIDE_BOTTOM,
    REGION_OXIDE_TOP,
    REGION_SILICON,
)


class Nanosheet2DBuilder(GeometryBuilder):
    """Double-gate 2D approximation of a gate-all-around nanosheet."""

    def build(self, msh_path: Path) -> MeshLayout:
        d, m = self.device, self.mesh
        msh_path = Path(msh_path)
        msh_path.parent.mkdir(parents=True, exist_ok=True)

        xs = [0.0, d.l_sd, d.l_sd + d.l_gate, d.l_total]
        ys = [-d.t_ox, 0.0, d.t_si, d.t_si + d.t_ox]
        nx = [m.nx_sd, m.nx_gate, m.nx_sd]
        ny = [m.ny_ox, m.ny_si, m.ny_ox]

        gmsh.initialize()
        try:
            gmsh.option.setNumber("General.Terminal", 0)
            gmsh.model.add("nanosheet2d")
            geo = gmsh.model.geo

            # 4x4 grid of points
            pts = [[geo.addPoint(x, y, 0.0) for y in ys] for x in xs]

            # horizontal lines h[i][j]: pts[i][j] -> pts[i+1][j]
            h = [[geo.addLine(pts[i][j], pts[i + 1][j]) for j in range(4)]
                 for i in range(3)]
            # vertical lines v[i][j]: pts[i][j] -> pts[i][j+1]
            v = [[geo.addLine(pts[i][j], pts[i][j + 1]) for j in range(3)]
                 for i in range(4)]

            # surfaces s[i][j]: column i (x block), row j (y block)
            s = [[None] * 3 for _ in range(3)]
            for i in range(3):
                for j in range(3):
                    loop = geo.addCurveLoop(
                        [h[i][j], v[i + 1][j], -h[i][j + 1], -v[i][j]])
                    s[i][j] = geo.addPlaneSurface([loop])

            geo.synchronize()

            # transfinite structured mesh
            for i in range(3):
                for j in range(4):
                    gmsh.model.mesh.setTransfiniteCurve(h[i][j], nx[i] + 1)
            for i in range(4):
                for j in range(3):
                    if j == 1:  # silicon body: refine toward both interfaces
                        gmsh.model.mesh.setTransfiniteCurve(
                            v[i][j], ny[j] + 1, "Bump", m.si_bump)
                    else:
                        gmsh.model.mesh.setTransfiniteCurve(v[i][j], ny[j] + 1)
            for i in range(3):
                for j in range(3):
                    gmsh.model.mesh.setTransfiniteSurface(s[i][j])

            # physical groups: regions (2D)
            gmsh.model.addPhysicalGroup(
                2, [s[i][0] for i in range(3)], name=REGION_OXIDE_BOTTOM)
            gmsh.model.addPhysicalGroup(
                2, [s[i][1] for i in range(3)], name=REGION_SILICON)
            gmsh.model.addPhysicalGroup(
                2, [s[i][2] for i in range(3)], name=REGION_OXIDE_TOP)

            # physical groups: contacts and interfaces (1D)
            gmsh.model.addPhysicalGroup(1, [v[0][1]], name=CONTACT_SOURCE)
            gmsh.model.addPhysicalGroup(1, [v[3][1]], name=CONTACT_DRAIN)
            gmsh.model.addPhysicalGroup(1, [h[1][0]], name=CONTACT_GATE_BOTTOM)
            gmsh.model.addPhysicalGroup(1, [h[1][3]], name=CONTACT_GATE_TOP)
            gmsh.model.addPhysicalGroup(
                1, [h[i][1] for i in range(3)], name=INTERFACE_SI_OX_BOTTOM)
            gmsh.model.addPhysicalGroup(
                1, [h[i][2] for i in range(3)], name=INTERFACE_SI_OX_TOP)

            gmsh.model.mesh.generate(2)
            gmsh.option.setNumber("Mesh.MshFileVersion", 2.2)
            gmsh.write(str(msh_path))
        finally:
            gmsh.finalize()

        return MeshLayout(
            dimension=2,
            regions={
                REGION_SILICON: "Silicon",
                REGION_OXIDE_TOP: "Oxide",
                REGION_OXIDE_BOTTOM: "Oxide",
            },
            contacts={
                CONTACT_SOURCE: REGION_SILICON,
                CONTACT_DRAIN: REGION_SILICON,
                CONTACT_GATE_TOP: REGION_OXIDE_TOP,
                CONTACT_GATE_BOTTOM: REGION_OXIDE_BOTTOM,
            },
            interfaces={
                INTERFACE_SI_OX_TOP: (REGION_SILICON, REGION_OXIDE_TOP),
                INTERFACE_SI_OX_BOTTOM: (REGION_SILICON, REGION_OXIDE_BOTTOM),
            },
        )
