"""Produce Fig.4/8/9-style figures from Jiang et al. (AMAT) for the
FBC/SBC CFET comparison, styled closer to the paper's own presentation:

  Fig. 4 (structure)         -> device render, warmer paper-like palette,
                                smooth shading, no mesh wireframe
  Fig. 8 (3D eMobility)      -> 3D render, turbo colormap (matches
                                Sentaurus Visual / TecPlot's field-plot
                                convention), translucent oxide context
  Fig. 9 (mobility profile)  -> the paper's actual Fig. 9 is a 2D
                                cross-sectional field map (a slice
                                perpendicular to transport), not a 1D
                                line plot - reproduced the same way here

Requires the two lombardi_vsat runs (configs/paper_{fbc,sbc}_lombardi_
cfet_3d.yaml) so mu_n_cvt/mu_p_cvt exist.

    python examples/paper_structure_mobility_figures.py RESULTS_ROOT -o docs
"""

import argparse
from pathlib import Path

import numpy as np

CONFIGS = ("paper_fbc_lombardi", "paper_sbc_lombardi")
LABELS = {"paper_fbc_lombardi": "FBC (fin, 5x18 nm)",
         "paper_sbc_lombardi": "SBC (sheet, 18x5 nm)"}
ORIENTATION = {"paper_fbc_lombardi": "(110)", "paper_sbc_lombardi": "(100)"}

# a warmer, paper-adjacent palette (kept local to this script; the GUI's
# own Structure 3D view keeps its existing blue/tan default)
SILICON_COLOR = "#9a4b3f"     # channel: warm brick, echoes the paper's NS
OXIDE_COLOR = "#d8bd85"       # gate oxide: gold/tan
CMAP = "turbo"                # vivid rainbow - the domain convention for
                              # TCAD field plots (Sentaurus Visual,
                              # TecPlot), not the general chart-design
                              # "avoid rainbow" advice, which is for
                              # generic business charts


def _region(meshes, sign: str):
    for m in meshes:
        if "NetDoping" not in m.array_names:
            continue
        if (sign == "n") == (float(np.asarray(m["NetDoping"]).sum()) > 0):
            return m
    raise ValueError(f"no {sign}-type silicon region in this snapshot")


def _full_bounds(meshes):
    b = np.array([m.bounds for m in meshes])
    return (b[:, 0].min(), b[:, 1].max(), b[:, 2].min(), b[:, 3].max(),
           b[:, 4].min(), b[:, 5].max())


def _own_oxide(oxides, region):
    """The oxide shell belonging to ``region``: the 3D GAA builder wraps
    each silicon channel in its own oxide shell whose y-range *encloses*
    the channel's (not just touches one face, unlike the 2D nanosheet's
    separate top/bottom layers) - so match by closest y-center instead
    of an edge-touching tolerance, which is geometry-independent."""
    y_mid = (region.bounds[2] + region.bounds[3]) / 2
    return min(oxides,
              key=lambda o: abs((o.bounds[2] + o.bounds[3]) / 2 - y_mid))


def _iso_camera(bounds, zoom=1.3):
    c = [(bounds[0] + bounds[1]) / 2, (bounds[2] + bounds[3]) / 2,
        (bounds[4] + bounds[5]) / 2]
    diag = float(np.linalg.norm(np.array(bounds[1::2]) - np.array(bounds[0::2])))
    return [[c[0] + zoom * diag, c[1] + 0.9 * zoom * diag,
             c[2] + 1.15 * zoom * diag], c, (0, 1, 0)], c


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
    from matplotlib.collections import PolyCollection

    from cfet_tcad.io.render3d import (load_snapshot, slice_polygons,
                                       snapshot_prefixes)

    meshes, nfet, pfet, oxides, device_bounds = {}, {}, {}, {}, {}
    for cfg in CONFIGS:
        vtk_dir = args.results_root / cfg / "vtk"
        prefix = snapshot_prefixes(vtk_dir)[-1]
        m = load_snapshot(vtk_dir, prefix)
        meshes[cfg] = m
        nfet[cfg] = _region(m, "n")
        pfet[cfg] = _region(m, "p")
        oxides[cfg] = [x for x in m if "NetDoping" not in x.array_names]
        device_bounds[cfg] = _full_bounds(m)

    # ---------------------------------------------------------------
    # Fig. 4 style: structure, warm palette, smooth shading, no edges
    # ---------------------------------------------------------------
    fig4 = args.out / "paper_fig4_structure.png"
    p = pv.Plotter(off_screen=True, shape=(1, 2), window_size=(1700, 900))
    for i, cfg in enumerate(CONFIGS):
        p.subplot(0, i)
        bounds = device_bounds[cfg]
        z_mid = (bounds[4] + bounds[5]) / 2
        for region in (nfet[cfg], pfet[cfg]):
            clipped = region.clip(normal="z", origin=[0, 0, z_mid])
            p.add_mesh(clipped, color=SILICON_COLOR, smooth_shading=True,
                      specular=0.4, specular_power=20, show_edges=False)
        for ox in oxides[cfg]:
            clipped = ox.clip(normal="z", origin=[0, 0, z_mid])
            p.add_mesh(clipped, color=OXIDE_COLOR, opacity=0.55,
                      smooth_shading=True, show_edges=False)
        p.add_text(f"{LABELS[cfg]}  -  channel {ORIENTATION[cfg]} surface",
                  font_size=13, color="black")
        p.camera_position, _ = _iso_camera(bounds)
    p.set_background("white")
    p.enable_anti_aliasing("ssaa")
    p.screenshot(str(fig4))
    p.close()
    print("wrote", fig4)

    # ---------------------------------------------------------------
    # Fig. 8 style: 3D eMobility, turbo colormap, oxide as context wrap
    # ---------------------------------------------------------------
    fig8 = args.out / "paper_fig8_emobility_3d.png"
    clim = (min(float(np.asarray(nfet[c]["mu_n_cvt"]).min()) for c in CONFIGS),
           max(float(np.asarray(nfet[c]["mu_n_cvt"]).max()) for c in CONFIGS))
    p = pv.Plotter(off_screen=True, shape=(1, 2), window_size=(1700, 900))
    for i, cfg in enumerate(CONFIGS):
        p.subplot(0, i)
        # isolate just the nFET + its own gate oxide - the paper's Fig.8
        # is a single-device eMobility plot, not the whole CFET stack
        n_region = nfet[cfg]
        n_oxide = _own_oxide(oxides[cfg], n_region)
        z_mid = (n_region.bounds[4] + n_region.bounds[5]) / 2
        clipped = n_region.clip(normal="z", origin=[0, 0, z_mid])
        p.add_mesh(clipped, scalars="mu_n_cvt", cmap=CMAP, clim=clim,
                  smooth_shading=True, show_edges=False,
                  scalar_bar_args={"title": "eMobility [cm2/Vs]",
                                  "color": "black"})
        oclip = n_oxide.clip(normal="z", origin=[0, 0, z_mid])
        p.add_mesh(oclip, color=OXIDE_COLOR, opacity=0.22,
                  smooth_shading=True, show_edges=False)
        p.add_text(f"{LABELS[cfg]} - nMOS eMobility {ORIENTATION[cfg]}",
                  font_size=12, color="black")
        p.camera_position, _ = _iso_camera(n_region.bounds, zoom=1.5)
    p.set_background("white")
    p.enable_anti_aliasing("ssaa")
    p.screenshot(str(fig8))
    p.close()
    print("wrote", fig8)

    # ---------------------------------------------------------------
    # Fig. 9 style: the paper's actual figure is a 2D cross-sectional
    # field map (a cut perpendicular to transport), not a line plot -
    # 4 panels: {SBC, FBC} x {nMOS eMobility, pMOS hMobility}
    # ---------------------------------------------------------------
    panels = [(cfg, field, carrier)
             for field, carrier in (("mu_n_cvt", "nMOS eMobility"),
                                    ("mu_p_cvt", "pMOS hMobility"))
             for cfg in CONFIGS]
    all_vals = {f: np.concatenate([
        np.asarray((nfet if f == "mu_n_cvt" else pfet)[c][f])
        for c in CONFIGS]) for f in ("mu_n_cvt", "mu_p_cvt")}
    clims = {f: (float(v.min()), float(v.max())) for f, v in all_vals.items()}

    fig, axes = plt.subplots(1, 4, figsize=(15, 4.4))
    fig.patch.set_facecolor("#fcfcfb")
    for ax, (cfg, field, carrier) in zip(axes, panels):
        region = nfet[cfg] if field == "mu_n_cvt" else pfet[cfg]
        x_mid = (region.bounds[0] + region.bounds[1]) / 2
        si_polys, si_vals = slice_polygons(region, "x", (x_mid, 0, 0),
                                           field=field)
        own_oxide = _own_oxide(oxides[cfg], region)
        ox_polys, _ = slice_polygons(own_oxide, "x", (x_mid, 0, 0))
        pc = PolyCollection([poly * 1e7 for poly in ox_polys],
                            facecolor=OXIDE_COLOR, edgecolor="none",
                            zorder=1)
        ax.add_collection(pc)
        pc = PolyCollection([poly * 1e7 for poly in si_polys], array=si_vals,
                            cmap=CMAP, edgecolor="none", zorder=2)
        pc.set_clim(*clims[field])
        ax.add_collection(pc)
        ax.autoscale_view()
        ax.set_aspect("equal")
        ax.set_facecolor("#fcfcfb")
        ax.set_xticks([]); ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_visible(False)
        label = "Sheet" if cfg == "paper_sbc_lombardi" else "Fin"
        ax.set_title(f"{label} {ORIENTATION[cfg]}\n{carrier}", fontsize=10)
        cbar = fig.colorbar(pc, ax=ax, fraction=0.046, pad=0.06)
        cbar.ax.tick_params(labelsize=7)
    fig.suptitle("Mobility distribution in the middle of channel "
                "(cross-section perpendicular to transport, paper Fig. 9 style)",
                fontsize=11)
    fig.tight_layout()
    fig9 = args.out / "paper_fig9_mobility_profile.png"
    fig.savefig(fig9, dpi=170)
    plt.close(fig)
    print("wrote", fig9)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
