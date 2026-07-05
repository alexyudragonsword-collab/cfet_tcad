"""DEVSIM mesh import: regions, contacts, and interfaces all arrive."""

import pytest

from cfet_tcad.geometry import DeviceParams, MeshParams, Nanosheet2DBuilder
from cfet_tcad.meshio_devsim import load_mesh


@pytest.fixture()
def coarse_mesh(tmp_path):
    msh = tmp_path / "dev.msh"
    layout = Nanosheet2DBuilder(
        DeviceParams(name="loadtest"),
        MeshParams(nx_sd=6, nx_gate=8, ny_si=4, ny_ox=2)).build(msh)
    return msh, layout


def test_load_creates_device(coarse_mesh, fresh_devsim):
    devsim = fresh_devsim
    msh, layout = coarse_mesh
    device = load_mesh(msh, layout, "loadtest")
    assert device in devsim.get_device_list()
    regions = set(devsim.get_region_list(device=device))
    assert regions == set(layout.regions)
    contacts = set(devsim.get_contact_list(device=device))
    assert contacts == set(layout.contacts)
    interfaces = set(devsim.get_interface_list(device=device))
    assert interfaces == set(layout.interfaces)


def test_node_coordinates_span_device(coarse_mesh, fresh_devsim):
    devsim = fresh_devsim
    msh, layout = coarse_mesh
    device = load_mesh(msh, layout, "loadtest")
    params = DeviceParams()
    xs = devsim.get_node_model_values(device=device, region="silicon",
                                      name="x")
    ys = devsim.get_node_model_values(device=device, region="silicon",
                                      name="y")
    assert min(xs) == pytest.approx(0.0, abs=1e-12)
    assert max(xs) == pytest.approx(params.l_total, rel=1e-6)
    assert min(ys) == pytest.approx(0.0, abs=1e-12)
    assert max(ys) == pytest.approx(params.t_si, rel=1e-6)
