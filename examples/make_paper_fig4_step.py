"""Generate the paper-Fig.4-style FBC CFET as a STEP assembly.

Builds the dual-fin complementary stack of the AMAT 3nm paper (nMOS
bottom, pMOS top, two fins each, gate-oxide shells around the channel
sections) with gmsh's OpenCASCADE kernel, in nanometers as CAD units,
and writes it as ``configs/paper_fbc_cfet_demo.step`` together with the
``import-step`` mapping spec.  This is the shipped end-to-end example
for the STEP import pipeline:

    cfet-tcad import-step configs/paper_fbc_cfet_demo_import.yaml
    cfet-tcad run configs/paper_fbc_cfet_demo_run.yaml

Dimensions follow configs/paper_fbc_cfet_3d.yaml (paper Fig. 2): fin
5 x 18 nm, Lg 15 nm, gate pitch 45 nm, fin pitch 26 nm, N/P space
30 nm, EOT ~1 nm.
"""

import argparse
from pathlib import Path

import yaml

# paper Fig. 2 dimensions [nm]
L_SD = 15.0
L_GATE = 15.0
FIN_W = 5.0       # along z
FIN_H = 18.0      # along y
T_OX = 1.0
FIN_PITCH = 26.0
NP_SPACE = 30.0
N_FINS = 2

L_TOTAL = 2 * L_SD + L_GATE
Y_P = FIN_H + NP_SPACE  # pMOS fins start here


def build_step(out_step: Path) -> None:
    import gmsh

    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("fbc_cfet")
        occ = gmsh.model.occ
        for y0 in (0.0, Y_P):                    # nFET bottom, pFET top
            for k in range(N_FINS):
                z0 = k * FIN_PITCH
                # the fin: S/D + channel as one continuous silicon bar
                occ.addBox(0, y0, z0, L_TOTAL, FIN_H, FIN_W)
                # gate-oxide shell wrapping the channel section on all
                # four sides (the rotated-GAA approximation the
                # parametric builder uses as well)
                outer = occ.addBox(L_SD, y0 - T_OX, z0 - T_OX, L_GATE,
                                   FIN_H + 2 * T_OX, FIN_W + 2 * T_OX)
                hole = occ.addBox(L_SD, y0, z0, L_GATE, FIN_H, FIN_W)
                occ.cut([(3, outer)], [(3, hole)])
        occ.synchronize()
        out_step.parent.mkdir(parents=True, exist_ok=True)
        gmsh.write(str(out_step))
    finally:
        gmsh.finalize()


def import_spec(step_name: str) -> dict:
    """The mapping spec: bbox selectors (a STEP written by gmsh carries
    no useful part names, and bboxes are the most portable teaching
    example anyway).  Small margins keep each box unambiguous: silicon
    boxes are tight in y so the shells (which stick out by T_OX) never
    fall inside them, and vice versa."""
    z_lo, z_hi = -3.0, (N_FINS - 1) * FIN_PITCH + FIN_W + 3.0

    def device(y0):
        si = [-0.5, y0 - 0.2, z_lo, L_TOTAL + 0.5, y0 + FIN_H + 0.2, z_hi]
        ox = [L_SD - 0.5, y0 - T_OX - 0.5, z_lo,
              L_SD + L_GATE + 0.5, y0 + FIN_H + T_OX + 0.5, z_hi]
        source = [0, y0 - 0.2, z_lo, 0, y0 + FIN_H + 0.2, z_hi]
        drain = [L_TOTAL, y0 - 0.2, z_lo, L_TOTAL, y0 + FIN_H + 0.2, z_hi]
        # gate metal = the shells' four LATERAL outer faces only (like
        # the parametric builder): thin slabs at the top/bottom planes
        # plus each shell's two z-side planes.  The axial end rings stay
        # uncontacted - metal meeting the S/D surface there creates a
        # triple-point field spike that wrecks convergence.
        x0, x1 = L_SD - 0.5, L_SD + L_GATE + 0.5
        gate = [[x0, y0 + FIN_H + T_OX - 0.2, z_lo,
                 x1, y0 + FIN_H + T_OX + 0.2, z_hi],
                [x0, y0 - T_OX - 0.2, z_lo, x1, y0 - T_OX + 0.2, z_hi]]
        for k in range(N_FINS):
            for zc in (k * FIN_PITCH - T_OX, k * FIN_PITCH + FIN_W + T_OX):
                gate.append([x0, y0 - T_OX - 0.5, zc - 0.2,
                             x1, y0 + FIN_H + T_OX + 0.5, zc + 0.2])
        return si, ox, source, drain, gate

    si_n, ox_n, src_n, drn_n, gate_n = device(0.0)
    si_p, ox_p, src_p, drn_p, gate_p = device(Y_P)
    return {
        "step_file": step_name,
        "unit_cm": 1.0e-7,          # drawn in nm
        "mesh_size": 2.0,
        "mesh_size_per_region": {"oxide_n": 1.0, "oxide_p": 1.0},
        "regions": {
            "silicon_n": {"select": {"bbox": si_n}, "material": "Silicon"},
            "oxide_n": {"select": {"bbox": ox_n}, "material": "Oxide"},
            "silicon_p": {"select": {"bbox": si_p}, "material": "Silicon"},
            "oxide_p": {"select": {"bbox": ox_p}, "material": "Oxide"},
        },
        "contacts": {
            "source_n": {"select": {"bbox": src_n}, "region": "silicon_n"},
            "drain_n": {"select": {"bbox": drn_n}, "region": "silicon_n"},
            "gate_n": {"select": {"bbox": gate_n}, "region": "oxide_n"},
            "source_p": {"select": {"bbox": src_p}, "region": "silicon_p"},
            "drain_p": {"select": {"bbox": drn_p}, "region": "silicon_p"},
            "gate_p": {"select": {"bbox": gate_p}, "region": "oxide_p"},
        },
        "interfaces": {
            "si_ox_n": ["silicon_n", "oxide_n"],
            "si_ox_p": ["silicon_p", "oxide_p"],
        },
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out-dir", type=Path, default=Path("configs"))
    ap.add_argument("--convert", action="store_true",
                    help="also run the conversion (self-check)")
    args = ap.parse_args(argv)

    step = args.out_dir / "paper_fbc_cfet_demo.step"
    spec_path = args.out_dir / "paper_fbc_cfet_demo_import.yaml"
    build_step(step)
    spec = import_spec(step.name)
    spec_path.write_text(yaml.safe_dump(spec, sort_keys=False),
                         encoding="utf-8")
    print(f"wrote {step} and {spec_path}")

    if args.convert:
        from cfet_tcad.geometry.step_import import convert_step
        msh = args.out_dir / "paper_fbc_cfet_demo.msh"
        summary = convert_step(spec, args.out_dir, msh)
        print(f"converted: {msh} ({summary['nodes']} nodes), "
              f"regions {summary['regions']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
