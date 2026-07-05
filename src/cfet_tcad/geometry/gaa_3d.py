"""3D gate-all-around single-nanosheet builder (gmsh built-in kernel).

Structure (units = cm): a silicon bar along x with rectangular cross
section t_si x W; the gate segment x in [L_sd, L_sd+L_g] is wrapped on all
four sides by a t_ox oxide shell whose outer surface is the gate contact.
Source/drain contacts sit on the bar's end faces; the S/D extensions are
bare (natural Neumann boundaries).

The device occupies a 3x3x3 block grid (x columns: source ext / gate /
drain ext; y rows and z rows: oxide / silicon / oxide):

- silicon: blocks (i, 1, 1), i = 0..2
- oxide:   blocks (1, j, k), (j, k) != (1, 1)   (4 slabs + 4 corner rods)

Everything is transfinite (structured tetrahedra).  The built-in geo
kernel is used deliberately: OCC's fixed 1e-7 internal precision is the
same order as the nm-scale feature sizes in cm units, whereas the geo
kernel trusts explicit topology and has no tolerance issues.
"""

from pathlib import Path

import gmsh

from .base import GeometryBuilder, MeshLayout
from .params import (
    CONTACT_DRAIN,
    CONTACT_GATE,
    CONTACT_SOURCE,
    INTERFACE_SI_OX,
    REGION_OXIDE,
    REGION_SILICON,
)


class _BlockGrid:
    """Structured 4x4x4-node block grid with create-on-demand gmsh
    entities.  Faces are keyed (normal_axis, i, j, k) by their min corner
    and oriented with the normal along +axis, so volume surface loops can
    be written with analytic signs."""

    def __init__(self, xs, ys, zs):
        self.geo = gmsh.model.geo
        self.coords = (xs, ys, zs)
        self.pts, self.lines, self.surfs, self.vols = {}, {}, {}, {}

    def point(self, i, j, k):
        key = (i, j, k)
        if key not in self.pts:
            self.pts[key] = self.geo.addPoint(
                self.coords[0][i], self.coords[1][j], self.coords[2][k], 0.0)
        return self.pts[key]

    def line(self, axis, i, j, k):
        """Line from grid node (i,j,k) to its +axis neighbor."""
        key = (axis, i, j, k)
        if key not in self.lines:
            nxt = [i, j, k]
            nxt[axis] += 1
            self.lines[key] = self.geo.addLine(self.point(i, j, k),
                                               self.point(*nxt))
        return self.lines[key]

    def surface(self, normal, i, j, k):
        key = (normal, i, j, k)
        if key not in self.surfs:
            if normal == 0:    # +x normal: loop +y, +z, -y, -z
                loop = [self.line(1, i, j, k), self.line(2, i, j + 1, k),
                        -self.line(1, i, j, k + 1), -self.line(2, i, j, k)]
            elif normal == 1:  # +y normal: loop +z, +x, -z, -x
                loop = [self.line(2, i, j, k), self.line(0, i, j, k + 1),
                        -self.line(2, i + 1, j, k), -self.line(0, i, j, k)]
            else:              # +z normal: loop +x, +y, -x, -y
                loop = [self.line(0, i, j, k), self.line(1, i + 1, j, k),
                        -self.line(0, i, j + 1, k), -self.line(1, i, j, k)]
            cl = self.geo.addCurveLoop(loop)
            self.surfs[key] = self.geo.addPlaneSurface([cl])
        return self.surfs[key]

    def volume(self, i, j, k):
        key = (i, j, k)
        if key not in self.vols:
            sl = self.geo.addSurfaceLoop([
                -self.surface(0, i, j, k), self.surface(0, i + 1, j, k),
                -self.surface(1, i, j, k), self.surface(1, i, j + 1, k),
                -self.surface(2, i, j, k), self.surface(2, i, j, k + 1)])
            self.vols[key] = self.geo.addVolume([sl])
        return self.vols[key]

    def set_transfinite(self, divisions):
        """divisions: per-axis element counts for the 3 grid segments."""
        for (axis, i, j, k), tag in self.lines.items():
            seg = (i, j, k)[axis]
            gmsh.model.mesh.setTransfiniteCurve(tag, divisions[axis][seg] + 1)
        for tag in self.surfs.values():
            gmsh.model.mesh.setTransfiniteSurface(tag)
        for tag in self.vols.values():
            gmsh.model.mesh.setTransfiniteVolume(tag)


class GAANanosheet3DBuilder(GeometryBuilder):
    """Single-nanosheet gate-all-around FET in full 3D."""

    def build(self, msh_path: Path) -> MeshLayout:
        d, m = self.device, self.mesh
        msh_path = Path(msh_path)
        msh_path.parent.mkdir(parents=True, exist_ok=True)

        w = d.sheet_width_nm * 1.0e-7  # cm
        xs = [0.0, d.l_sd, d.l_sd + d.l_gate, d.l_total]
        ys = [-d.t_ox, 0.0, d.t_si, d.t_si + d.t_ox]
        zs = [-d.t_ox, 0.0, w, w + d.t_ox]
        divisions = [
            [m.nx_sd, m.nx_gate, m.nx_sd],
            [m.ny_ox, m.ny_si, m.ny_ox],
            [m.ny_ox, m.nz_w, m.ny_ox],
        ]

        silicon_blocks = [(i, 1, 1) for i in range(3)]
        oxide_blocks = [(1, j, k) for j in range(3) for k in range(3)
                        if (j, k) != (1, 1)]

        gmsh.initialize()
        try:
            gmsh.option.setNumber("General.Terminal", 0)
            gmsh.model.add("gaa3d")
            grid = _BlockGrid(xs, ys, zs)

            si_vols = [grid.volume(*b) for b in silicon_blocks]
            ox_vols = [grid.volume(*b) for b in oxide_blocks]
            grid.geo.synchronize()
            grid.set_transfinite(divisions)

            gmsh.model.addPhysicalGroup(3, si_vols, name=REGION_SILICON)
            gmsh.model.addPhysicalGroup(3, ox_vols, name=REGION_OXIDE)

            # contacts: S/D on the bar end faces, gate on the shell's outer
            # lateral faces (12 faces: 4 sides x 3 cross-section cells)
            gmsh.model.addPhysicalGroup(2, [grid.surface(0, 0, 1, 1)],
                                        name=CONTACT_SOURCE)
            gmsh.model.addPhysicalGroup(2, [grid.surface(0, 3, 1, 1)],
                                        name=CONTACT_DRAIN)
            gate_faces = (
                [grid.surface(1, 1, 0, k) for k in range(3)] +   # y = min
                [grid.surface(1, 1, 3, k) for k in range(3)] +   # y = max
                [grid.surface(2, 1, j, 0) for j in range(3)] +   # z = min
                [grid.surface(2, 1, j, 3) for j in range(3)])    # z = max
            gmsh.model.addPhysicalGroup(2, gate_faces, name=CONTACT_GATE)

            # silicon/oxide interface: the 4 lateral faces of the channel
            iface = [grid.surface(1, 1, 1, 1), grid.surface(1, 1, 2, 1),
                     grid.surface(2, 1, 1, 1), grid.surface(2, 1, 1, 2)]
            gmsh.model.addPhysicalGroup(2, iface, name=INTERFACE_SI_OX)

            gmsh.model.mesh.generate(3)
            gmsh.option.setNumber("Mesh.MshFileVersion", 2.2)
            gmsh.write(str(msh_path))
        finally:
            gmsh.finalize()

        return MeshLayout(
            dimension=3,
            regions={REGION_SILICON: "Silicon", REGION_OXIDE: "Oxide"},
            contacts={
                CONTACT_SOURCE: REGION_SILICON,
                CONTACT_DRAIN: REGION_SILICON,
                CONTACT_GATE: REGION_OXIDE,
            },
            interfaces={INTERFACE_SI_OX: (REGION_SILICON, REGION_OXIDE)},
        )
