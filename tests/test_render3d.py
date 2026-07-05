"""3D rendering: structure snapshot CLI and offscreen PyVista renders.

Skipped when the viz extra (pyvista) is not installed.
"""

import numpy as np
import pytest

pv = pytest.importorskip("pyvista")

from cfet_tcad.workflow.cli import main as cli_main  # noqa: E402


@pytest.fixture(scope="module")
def structure_dir(tmp_path_factory):
    """A 3D CFET structure snapshot produced through the CLI (no solve)."""
    out = tmp_path_factory.mktemp("struct")
    cfg = out / "cfg.yaml"
    cfg.write_text("""
device: {name: r3d, structure: cfet_3d}
mesh: {nx_sd: 4, nx_gate: 6, ny_si: 3, ny_ox: 2, nz_w: 4}
""")
    # run in-process: devsim state is fine for a single structure export
    assert cli_main(["structure", str(cfg), "-o", str(out)]) == 0
    return out / "vtk"


def test_structure_snapshot_produces_regions(structure_dir):
    from cfet_tcad.io.render3d import load_snapshot, snapshot_prefixes

    prefixes = snapshot_prefixes(structure_dir)
    assert prefixes == ["structure"]
    meshes = load_snapshot(structure_dir)
    assert len(meshes) == 4  # silicon_n/p + oxide_n/p
    semis = [m for m in meshes if "NetDoping" in m.array_names]
    assert len(semis) == 2
    # one sheet donor-doped, one acceptor-doped
    signs = sorted(float(np.sign(np.asarray(m["NetDoping"]).sum()))
                   for m in semis)
    assert signs == [-1.0, 1.0]


def test_field_choices(structure_dir):
    from cfet_tcad.io.render3d import field_choices, load_snapshot

    choices = field_choices(load_snapshot(structure_dir))
    assert choices[0] == "Structure"
    assert "NetDoping" in choices
    assert "Potential" not in choices  # structure-only export, no solve


@pytest.mark.parametrize("ext", [".stl", ".ply", ".vtp"])
def test_export_surface(structure_dir, tmp_path, ext):
    """Design export: boundary surface files load back with real cells
    (pure mesh processing, no GL involved)."""
    from cfet_tcad.io.render3d import export_surface

    path = export_surface(structure_dir, tmp_path / f"dev{ext}")
    assert path.exists() and path.stat().st_size > 0
    back = pv.read(path)
    assert back.n_cells > 0
    if ext == ".stl":  # STL is triangles-only
        assert back.is_all_triangles


def test_export_obj_with_materials(structure_dir, tmp_path):
    """Colored OBJ export (off-screen render, same GL needs as PNGs)."""
    from cfet_tcad.io.render3d import export_obj

    path = export_obj(structure_dir, tmp_path / "dev.obj")
    assert path.exists() and path.stat().st_size > 0
    assert (tmp_path / "dev.mtl").exists()  # material colors ride along


@pytest.mark.parametrize("field,clip", [(None, None), ("NetDoping", "z")])
def test_offscreen_render_nonblank(structure_dir, tmp_path, field, clip):
    from cfet_tcad.io.render3d import render_structure

    png = tmp_path / "r.png"
    render_structure(structure_dir, png=png, field=field, clip=clip,
                     window_size=(320, 240))
    from PIL import Image
    img = np.array(Image.open(png))
    assert img.shape[:2] == (240, 320)
    # a real render has many distinct colors; a blank canvas has ~1
    assert len(np.unique(img.reshape(-1, img.shape[2]), axis=0)) > 10


@pytest.fixture(scope="module")
def lombardi_vtk_dir(tmp_path_factory):
    """A tiny lombardi_vsat solve at a single high-Vg bias: the mobility
    fields (mu_*_lf_node, mu_*_cvt) only exist post-solve, unlike the
    structure-only fixture above."""
    import cfet_tcad
    cfet_tcad.reset()  # the structure_dir fixture left its device behind

    out = tmp_path_factory.mktemp("lombardi")
    cfg = out / "cfg.yaml"
    cfg.write_text("""
device: {name: lomb, polarity: n, gate_workfunction_ev: 4.5}
mesh: {nx_sd: 6, nx_gate: 10, ny_si: 5, ny_ox: 2}
physics: {mobility_model: lombardi_vsat}
simulation: {type: idvg, vd: [0.7], vg_start: 0.6, vg_stop: 0.65, vg_step: 0.05}
output: {directory: unused, vtk: true}
""")
    assert cli_main(["run", str(cfg), "-o", str(out)]) == 0
    return out / "vtk"


def test_field_choices_includes_mobility(lombardi_vtk_dir):
    from cfet_tcad.io.render3d import field_choices, load_snapshot

    choices = field_choices(load_snapshot(lombardi_vtk_dir))
    # low-field (point data) and full CVT (DEVSIM's own cell data) both
    # ride along automatically - no export code of our own involved
    for f in ("mu_n_lf_node", "mu_n_cvt"):
        assert f in choices, choices


def test_add_device_colors_by_cell_data_mobility(lombardi_vtk_dir, tmp_path):
    """mu_n_cvt only exists as VTK cell data; add_device's generic field
    path must resolve it (pyvista searches point then cell data)."""
    from cfet_tcad.io.render3d import render_structure

    png = tmp_path / "mu.png"
    render_structure(lombardi_vtk_dir, png=png, field="mu_n_cvt",
                     window_size=(320, 240))
    from PIL import Image
    img = np.array(Image.open(png))
    assert len(np.unique(img.reshape(-1, img.shape[2]), axis=0)) > 10


def test_sample_line_mobility_profile(lombardi_vtk_dir):
    """A 1D cut across the channel (paper Fig. 9 style): cell data is
    averaged onto points first, so the profile is a plain smooth curve."""
    from cfet_tcad.io.render3d import load_snapshot, sample_line

    meshes = load_snapshot(lombardi_vtk_dir)
    semis = [m for m in meshes if "mu_n_cvt" in m.array_names]
    assert semis
    bounds = semis[0].bounds  # (xmin,xmax,ymin,ymax,zmin,zmax)
    x_mid = (bounds[0] + bounds[1]) / 2
    p1 = (x_mid, bounds[2], 0.0)
    p2 = (x_mid, bounds[3], 0.0)
    distance, values = sample_line(meshes, "mu_n_cvt", p1, p2, resolution=50)
    assert len(distance) == len(values) == 51
    assert np.all(values > 0)  # a real mobility profile, not all-NaN/zero

    missing_d, missing_v = sample_line(meshes, "not_a_field", p1, p2)
    assert len(missing_d) == 0 and len(missing_v) == 0


def test_slice_polygons_cross_section(lombardi_vtk_dir):
    """Paper Fig. 9 is a cross-sectional field map, not a line profile:
    a slice perpendicular to transport gives per-cell 2D polygons."""
    from cfet_tcad.io.render3d import load_snapshot, slice_polygons

    meshes = load_snapshot(lombardi_vtk_dir)
    silicon = next(m for m in meshes if "mu_n_cvt" in m.array_names)
    x_mid = (silicon.bounds[0] + silicon.bounds[1]) / 2
    polygons, values = slice_polygons(silicon, "x", (x_mid, 0, 0),
                                      field="mu_n_cvt")
    assert len(polygons) == len(values) > 0
    for poly in polygons:
        assert poly.shape[1] == 2  # normal axis dropped
    assert np.all(values > 0)

    empty_polys, empty_vals = slice_polygons(
        silicon, "x", (silicon.bounds[1] + 1, 0, 0), field="mu_n_cvt")
    assert empty_polys == [] and len(empty_vals) == 0  # plane misses mesh
