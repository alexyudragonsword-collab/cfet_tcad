"""3D device rendering on PyVista/VTK (Sentaurus Visual's technology).

Consumes the per-region ``.vtu`` files DEVSIM writes (one per region, all
sharing a filename prefix) and builds a scene colored either by material
(structure view: silicon opaque, oxides translucent) or by a node field
(NetDoping with a symmetric-log scale, Potential, Electrons, ...).

Qt-free: usable headlessly (off_screen screenshot) and from the GUI (pass
an existing plotter, e.g. a pyvistaqt QtInteractor).
"""

import math
import re
from pathlib import Path

import numpy as np
import pyvista as pv

#: material colors keyed by substring of the region filename index — the
#: DEVSIM .vtm lists regions in creation order, but the robust cue is the
#: field content: regions with doping arrays are semiconductors
SEMI_COLOR = "#4f7cac"
OXIDE_COLOR = "#d9c589"


def snapshot_prefixes(vtk_dir: Path) -> list[str]:
    """Distinct snapshot prefixes in a vtk output directory, sorted.

    DEVSIM writes ``<prefix>_<k>.vtu`` per region plus ``<prefix>.vtm``;
    sweep snapshots differ in prefix (e.g. idvg_vdp0.700_014)."""
    seen = []
    for vtm in sorted(Path(vtk_dir).glob("*.vtm")):
        seen.append(vtm.stem)
    return seen


def load_snapshot(vtk_dir: Path, prefix: str | None = None) -> list[pv.DataSet]:
    """Read all region meshes of one snapshot (default: last prefix)."""
    vtk_dir = Path(vtk_dir)
    if prefix is None:
        prefixes = snapshot_prefixes(vtk_dir)
        if not prefixes:
            raise FileNotFoundError(f"no .vtm snapshots in {vtk_dir}")
        prefix = prefixes[-1]
    pattern = re.compile(re.escape(prefix) + r"_(\d+)\.vtu$")
    files = sorted((p for p in vtk_dir.glob(f"{prefix}_*.vtu")
                    if pattern.search(p.name)),
                   key=lambda p: int(pattern.search(p.name).group(1)))
    if not files:
        raise FileNotFoundError(f"no {prefix}_*.vtu in {vtk_dir}")
    return [pv.read(f) for f in files]


def _is_semiconductor(mesh: pv.DataSet) -> bool:
    return "NetDoping" in mesh.array_names


def _signed_log(values: np.ndarray) -> np.ndarray:
    """Symmetric log for doping: sign(N) * log10(1 + |N|)."""
    return np.sign(values) * np.log10(1.0 + np.abs(values))


def add_device(plotter: pv.Plotter, meshes: list[pv.DataSet],
               field: str | None = None, clip: str | None = None) -> None:
    """Add the device to a plotter.

    field=None  -> structure view (materials); otherwise color by the
    node array (semiconductor regions; insulators stay translucent).
    clip="y"/"z" cuts the device open at the mid-plane.
    """
    bounds = np.array([m.bounds for m in meshes])
    center = [(bounds[:, 0].min() + bounds[:, 1].max()) / 2,
              (bounds[:, 2].min() + bounds[:, 3].max()) / 2,
              (bounds[:, 4].min() + bounds[:, 5].max()) / 2]

    def prep(mesh):
        if clip in ("y", "z"):
            return mesh.clip(normal=clip, origin=center, invert=False)
        return mesh

    semis = [m for m in meshes if _is_semiconductor(m)]
    others = [m for m in meshes if not _is_semiconductor(m)]

    if field is None or field == "Structure":
        for m in semis:
            plotter.add_mesh(prep(m), color=SEMI_COLOR, show_edges=True,
                             edge_opacity=0.15)
        for m in others:
            plotter.add_mesh(prep(m), color=OXIDE_COLOR, opacity=0.35)
        return

    if field == "NetDoping":
        limit = 0.0
        for m in semis:
            m = m.copy()
            m["signed log10 NetDoping"] = _signed_log(
                np.asarray(m["NetDoping"]))
            limit = max(limit, float(np.abs(
                m["signed log10 NetDoping"]).max()))
            m.set_active_scalars("signed log10 NetDoping")
            plotter.add_mesh(prep(m), scalars="signed log10 NetDoping",
                             cmap="coolwarm", clim=(-limit, limit),
                             show_edges=False)
    else:
        log_fields = ("Electrons", "Holes")
        for m in semis:
            if field not in m.array_names:
                continue
            m = m.copy()
            if field in log_fields:
                name = f"log10 {field}"
                m[name] = np.log10(np.maximum(np.asarray(m[field]), 1.0))
            else:
                name = field
            m.set_active_scalars(name)
            plotter.add_mesh(prep(m), scalars=name, cmap="viridis")
    for m in others:
        plotter.add_mesh(prep(m), color=OXIDE_COLOR, opacity=0.15)


def render_structure(vtk_dir: Path, png: Path | None = None,
                     field: str | None = None, clip: str | None = None,
                     prefix: str | None = None,
                     plotter: pv.Plotter | None = None,
                     window_size=(1100, 800)) -> pv.Plotter:
    """Render one snapshot; screenshot to ``png`` when no plotter given."""
    meshes = load_snapshot(vtk_dir, prefix)
    own = plotter is None
    if own:
        plotter = pv.Plotter(off_screen=True, window_size=list(window_size))
    add_device(plotter, meshes, field=field, clip=clip)
    plotter.add_axes()
    # nm-scale device in cm units: isometric view with a slight elevation
    plotter.camera_position = "iso"
    plotter.camera.zoom(1.2)
    if own:
        plotter.set_background("white")
        if png is not None:
            plotter.screenshot(str(png))
    return plotter


def field_choices(meshes: list[pv.DataSet]) -> list[str]:
    """Node fields worth offering in a UI, present in any region."""
    interesting = ("NetDoping", "Potential", "Electrons", "Holes",
                   "Lambda_n", "Lambda_p")
    present = set()
    for m in meshes:
        present.update(m.array_names)
    return ["Structure"] + [f for f in interesting if f in present]
