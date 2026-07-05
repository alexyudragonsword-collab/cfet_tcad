"""Produce Fig.4/8/9-style figures from Jiang et al. (AMAT) for the
FBC/SBC CFET comparison, using this program's own capabilities:

  Fig. 4 (structure)         -> device cross-section render (Structure)
  Fig. 8 (3D eMobility)      -> 3D render colored by mu_n_cvt (CVT mobility)
  Fig. 9 (mobility profile)  -> 1D cut across the confinement direction

Requires the two lombardi_vsat runs (configs/paper_{fbc,sbc}_lombardi_
cfet_3d.yaml) so mu_n_cvt/mu_p_cvt exist (only lombardi_vsat assembles
them; the earlier doping_vsat paper_{fbc,sbc}_cfet_3d.yaml runs used for
the Ion/Ioff comparison do not carry this field).

    python examples/paper_structure_mobility_figures.py RESULTS_ROOT -o docs
"""

import argparse
from pathlib import Path

import numpy as np

CONFIGS = ("paper_fbc_lombardi", "paper_sbc_lombardi")
LABELS = {"paper_fbc_lombardi": "FBC (fin, 5x18 nm)",
         "paper_sbc_lombardi": "SBC (sheet, 18x5 nm)"}
COLORS = {"paper_fbc_lombardi": "#2a78d6", "paper_sbc_lombardi": "#1baf7a"}

#: inset the line-sample endpoints away from the exact oxide interface -
#: sample_over_line probing precisely on the mesh boundary can miss every
#: cell and silently return 0, which would masquerade as real data
_INSET = 0.03


def _region(meshes, sign: str):
    """The silicon region matching a doping sign ('n' -> donor-dominated,
    'p' -> acceptor-dominated) - never assume file/creation order."""
    for m in meshes:
        if "NetDoping" not in m.array_names:
            continue
        total = float(np.asarray(m["NetDoping"]).sum())
        if (sign == "n") == (total > 0):
            return m
    raise ValueError(f"no {sign}-type silicon region in this snapshot")


def _full_bounds(meshes):
    b = np.array([m.bounds for m in meshes])
    return (b[:, 0].min(), b[:, 1].max(), b[:, 2].min(), b[:, 3].max(),
           b[:, 4].min(), b[:, 5].max())


def _iso_camera(bounds):
    c = [(bounds[0] + bounds[1]) / 2, (bounds[2] + bounds[3]) / 2,
        (bounds[4] + bounds[5]) / 2]
    diag = float(np.linalg.norm(np.array(bounds[1::2]) - np.array(bounds[0::2])))
    return [[c[0] + 1.3 * diag, c[1] + 1.1 * diag, c[2] + 1.4 * diag],
           c, (0, 1, 0)], c


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("results_root", type=Path)
    ap.add_argument("-o", "--out", type=Path, default=Path("docs"))
    args = ap.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import pyvista as pv

    from cfet_tcad.io.render3d import (add_device, load_snapshot,
                                       sample_line, snapshot_prefixes)

    meshes, device_bounds, nfet, pfet = {}, {}, {}, {}
    for cfg in CONFIGS:
        vtk_dir = args.results_root / cfg / "vtk"
        prefix = snapshot_prefixes(vtk_dir)[-1]  # the high-Vg snapshot
        m = load_snapshot(vtk_dir, prefix)
        meshes[cfg] = m
        device_bounds[cfg] = _full_bounds(m)
        nfet[cfg] = _region(m, "n")
        pfet[cfg] = _region(m, "p")

    # --- Fig. 4 style: structure cross-sections, FBC vs SBC -------------
    fig4 = args.out / "paper_fig4_structure.png"
    p = pv.Plotter(off_screen=True, shape=(1, 2), window_size=(1600, 750))
    for i, cfg in enumerate(CONFIGS):
        p.subplot(0, i)
        add_device(p, meshes[cfg], field=None, clip="z")
        p.add_text(LABELS[cfg], font_size=12)
        p.add_axes()
        p.camera_position, _ = _iso_camera(device_bounds[cfg])
    p.set_background("white")
    p.screenshot(str(fig4))
    p.close()
    print("wrote", fig4)

    # --- Fig. 8 style: 3D eMobility (mu_n_cvt) distribution --------------
    fig8 = args.out / "paper_fig8_emobility_3d.png"
    clim = (min(float(np.asarray(nfet[c]["mu_n_cvt"]).min()) for c in CONFIGS),
           max(float(np.asarray(nfet[c]["mu_n_cvt"]).max()) for c in CONFIGS))
    p = pv.Plotter(off_screen=True, shape=(1, 2), window_size=(1600, 750))
    for i, cfg in enumerate(CONFIGS):
        p.subplot(0, i)
        cam, center = _iso_camera(device_bounds[cfg])
        clipped = nfet[cfg].clip(normal="z", origin=center)
        p.add_mesh(clipped, scalars="mu_n_cvt", cmap="viridis", clim=clim,
                  scalar_bar_args={"title": "eMobility [cm2/Vs]"})
        p.add_text(f"{LABELS[cfg]} - nMOS eMobility", font_size=11)
        p.add_axes()
        p.camera_position = cam
    p.set_background("white")
    p.screenshot(str(fig8))
    p.close()
    print("wrote", fig8)

    # --- Fig. 9 style: mobility profile across the confinement direction
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4))
    fig.patch.set_facecolor("#fcfcfb")
    plots = ((axes[0], "mu_n_cvt", nfet, "nMOS (electron) eMobility"),
             (axes[1], "mu_p_cvt", pfet, "pMOS (hole) eMobility"))
    for ax, field, region_of, title in plots:
        for cfg in CONFIGS:
            b = region_of[cfg].bounds
            x_mid = (b[0] + b[1]) / 2
            z_mid = (b[4] + b[5]) / 2
            span = b[3] - b[2]
            y0, y1 = b[2] + _INSET * span, b[3] - _INSET * span
            dist, vals = sample_line(meshes[cfg], field,
                                     (x_mid, y0, z_mid), (x_mid, y1, z_mid),
                                     resolution=150)
            t_si_nm = span * 1e7  # cm -> nm
            ax.plot(dist * 1e7, vals, color=COLORS[cfg], lw=2,
                   label=f"{LABELS[cfg]} (t_si={t_si_nm:.0f}nm)")
        ax.set_xlabel("position across confinement direction [nm]")
        ax.set_ylabel("mobility [cm2/Vs]")
        ax.set_ylim(0, None)
        ax.set_title(title, fontsize=10)
        ax.grid(True, alpha=0.25)
        ax.legend(fontsize=8)
    fig.suptitle("Mobility profile across the channel body "
                "(paper Fig. 9 style; oxide interfaces at both ends)",
                fontsize=11)
    fig.tight_layout()
    fig9 = args.out / "paper_fig9_mobility_profile.png"
    fig.savefig(fig9, dpi=160)
    plt.close(fig)
    print("wrote", fig9)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
