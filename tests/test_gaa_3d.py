"""3D GAA builder: mesh generation, DEVSIM import, equilibrium smoke."""

import pytest

from cfet_tcad.geometry import DeviceParams, GAANanosheet3DBuilder, MeshParams
from cfet_tcad.geometry.params import (
    CONTACT_DRAIN,
    CONTACT_GATE,
    CONTACT_SOURCE,
    INTERFACE_SI_OX,
    REGION_OXIDE,
    REGION_SILICON,
)
from cfet_tcad.meshio_devsim import load_mesh

COARSE = MeshParams(nx_sd=4, nx_gate=6, ny_si=3, ny_ox=2, nz_w=4)


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    msh = tmp_path_factory.mktemp("mesh3d") / "gaa.msh"
    params = DeviceParams(name="gaa_t", structure="gaa_3d")
    layout = GAANanosheet3DBuilder(params, COARSE).build(msh)
    return msh, layout


def test_layout_contract_3d(built):
    _, layout = built
    assert layout.dimension == 3
    assert layout.regions == {REGION_SILICON: "Silicon",
                              REGION_OXIDE: "Oxide"}
    assert layout.contacts == {CONTACT_SOURCE: REGION_SILICON,
                               CONTACT_DRAIN: REGION_SILICON,
                               CONTACT_GATE: REGION_OXIDE}
    assert layout.interfaces == {INTERFACE_SI_OX: (REGION_SILICON,
                                                   REGION_OXIDE)}


def test_msh_has_3d_groups(built):
    msh, _ = built
    text = msh.read_text()
    assert text.startswith("$MeshFormat\n2.2 0 8")
    for name in (REGION_SILICON, REGION_OXIDE, CONTACT_SOURCE,
                 CONTACT_DRAIN, CONTACT_GATE, INTERFACE_SI_OX):
        assert f'"{name}"' in text


def test_load_3d_device(built, fresh_devsim):
    devsim = fresh_devsim
    msh, layout = built
    device = load_mesh(msh, layout, "gaa_t")
    assert set(devsim.get_region_list(device=device)) == set(layout.regions)
    assert set(devsim.get_contact_list(device=device)) == set(layout.contacts)
    # silicon spans the full bar; oxide shell only the gate segment
    params = DeviceParams()
    xs = devsim.get_node_model_values(device=device, region="silicon",
                                      name="x")
    assert max(xs) == pytest.approx(params.l_total, rel=1e-6)
    xo = devsim.get_node_model_values(device=device, region="oxide", name="x")
    assert min(xo) == pytest.approx(params.l_sd, rel=1e-6)
    assert max(xo) == pytest.approx(params.l_sd + params.l_gate, rel=1e-6)


def test_equilibrium_converges_3d(tmp_path, fresh_devsim):
    devsim = fresh_devsim
    params = DeviceParams(name="gaa_eq", structure="gaa_3d",
                          gate_workfunction_ev=4.50)
    msh = tmp_path / "gaa.msh"
    layout = GAANanosheet3DBuilder(params, COARSE).build(msh)
    device = load_mesh(msh, layout, params.name)

    from cfet_tcad.solve import setup_equilibrium
    setup_equilibrium(device, layout, params)

    pot = devsim.get_node_model_values(device=device, region="silicon",
                                       name="Potential")
    assert -0.7 < min(pot) < max(pot) < 0.7
