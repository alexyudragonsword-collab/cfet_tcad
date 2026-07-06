"""Generate the paper-style SBC (sheet-based) CFET as a STEP assembly.

The sheet-based counterpart to examples/make_paper_fig4_step.py: two
horizontal nanosheets stacked vertically per device (nMOS bottom, pMOS
top), each wrapped by a gate-oxide shell over its channel section, built
with gmsh's OpenCASCADE kernel in nanometers as CAD units.  Writes
``configs/paper_sbc_cfet_demo.step`` plus its ``import-step`` mapping
spec - the shipped SBC example for the STEP import pipeline:

    cfet-tcad import-step configs/paper_sbc_cfet_demo_import.yaml
    cfet-tcad run configs/paper_sbc_cfet_demo_run.yaml

Dimensions follow configs/paper_sbc_cfet_3d.yaml (paper Fig. 2):
nanosheet 18 wide x 5 thick nm, Lg 15 nm, sheet pitch 15 nm, N/P space
30 nm, EOT ~1 nm.  The only geometric difference from the FBC demo is
the channel cross-section and that the two channels stack along y
(the fins sat side by side along z).
"""

import argparse
from pathlib import Path

import yaml

# paper Fig. 2 dimensions [nm]
L_SD = 15.0
L_GATE = 15.0
SHEET_W = 18.0     # along z
SHEET_H = 5.0      # along y (thickness)
T_OX = 1.0
SHEET_PITCH = 15.0
NP_SPACE = 30.0
N_SHEETS = 2

L_TOTAL = 2 * L_SD + L_GATE
DEV_H = (N_SHEETS - 1) * SHEET_PITCH + SHEET_H  # one device's y extent
Y_P = DEV_H + NP_SPACE                          # pMOS stack starts here


def build_step(out_step: Path) -> None:
    import gmsh

    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("sbc_cfet")
        occ = gmsh.model.occ
        for y_base in (0.0, Y_P):                 # nFET bottom, pFET top
            for k in range(N_SHEETS):
                y0 = y_base + k * SHEET_PITCH      # sheets stack along y
                # the sheet: S/D + channel as one continuous silicon bar
                occ.addBox(0, y0, 0, L_TOTAL, SHEET_H, SHEET_W)
                # gate-oxide shell wrapping the channel section on all
                # four sides (the GAA all-around approximation)
                outer = occ.addBox(L_SD, y0 - T_OX, -T_OX, L_GATE,
                                   SHEET_H + 2 * T_OX, SHEET_W + 2 * T_OX)
                hole = occ.addBox(L_SD, y0, 0, L_GATE, SHEET_H, SHEET_W)
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
    z_lo, z_hi = -T_OX - 3.0, SHEET_W + T_OX + 3.0

    def device(y_base):
        y_lo = y_base - T_OX - 0.5
        y_hi = y_base + (N_SHEETS - 1) * SHEET_PITCH + SHEET_H + T_OX + 0.5
        si = [-0.5, y_base - 0.2, -0.5,
              L_TOTAL + 0.5, y_hi, SHEET_W + 0.5]
        ox = [L_SD - 0.5, y_base - T_OX - 0.2, -T_OX - 0.2,
              L_SD + L_GATE + 0.5, y_hi, SHEET_W + T_OX + 0.2]
        source = [0, y_base - 0.2, -0.2, 0, y_hi, SHEET_W + 0.2]
        drain = [L_TOTAL, y_base - 0.2, -0.2, L_TOTAL, y_hi, SHEET_W + 0.2]
        # gate metal = the shells' four LATERAL outer faces only (like
        # the parametric builder): the two z-side planes span every
        # sheet, plus each sheet's own top/bottom y-planes (the axial
        # end rings stay uncontacted - metal on the S/D end surface
        # there makes a triple-point field spike that wrecks
        # convergence).  This is the FBC gate layout with y<->z swapped
        # because the channels stack along y here.
        x0, x1 = L_SD - 0.5, L_SD + L_GATE + 0.5
        gate = [[x0, y_lo, SHEET_W + T_OX - 0.2, x1, y_hi, SHEET_W + T_OX + 0.2],
                [x0, y_lo, -T_OX - 0.2, x1, y_hi, -T_OX + 0.2]]
        for k in range(N_SHEETS):
            ys = y_base + k * SHEET_PITCH
            for yc in (ys - T_OX, ys + SHEET_H + T_OX):
                gate.append([x0, yc - 0.2, -T_OX - 0.5,
                             x1, yc + 0.2, SHEET_W + T_OX + 0.5])
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

    step = args.out_dir / "paper_sbc_cfet_demo.step"
    spec_path = args.out_dir / "paper_sbc_cfet_demo_import.yaml"
    build_step(step)
    spec = import_spec(step.name)
    spec_path.write_text(yaml.safe_dump(spec, sort_keys=False),
                         encoding="utf-8")
    print(f"wrote {step} and {spec_path}")

    if args.convert:
        from cfet_tcad.geometry.step_import import convert_step
        msh = args.out_dir / "paper_sbc_cfet_demo.msh"
        summary = convert_step(spec, args.out_dir, msh)
        print(f"converted: {msh} ({summary['nodes']} nodes), "
              f"regions {summary['regions']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
