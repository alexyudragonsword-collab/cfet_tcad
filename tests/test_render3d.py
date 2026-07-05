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
