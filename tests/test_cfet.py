"""CFET stack: layout contract, mesh integrity, coupled equilibrium."""

import pytest

from cfet_tcad.geometry import CFETStack2DBuilder, DeviceParams, MeshParams
from cfet_tcad.meshio_devsim import load_mesh
from cfet_tcad.solve import setup_equilibrium

PARAMS = DeviceParams(name="cfet_t", structure="cfet_2d")
COARSE = MeshParams(nx_sd=8, nx_gate=12, ny_si=6, ny_ox=2)


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    msh = tmp_path_factory.mktemp("cfet") / "cfet.msh"
    layout = CFETStack2DBuilder(PARAMS, COARSE).build(msh)
    return msh, layout


def test_layout_contract(built):
    _, layout = built
    assert set(layout.regions) == {
        "silicon_n", "silicon_p",
        "oxide_n_top", "oxide_n_bottom", "oxide_p_top", "oxide_p_bottom"}
    assert set(layout.contacts) == {
        "source_n", "drain_n", "source_p", "drain_p",
        "gate_top", "gate_mid_n", "gate_mid_p", "gate_bottom"}
    assert layout.silicon_polarity == {"silicon_n": "n", "silicon_p": "p"}
    wf = layout.gate_workfunctions
    assert wf["gate_top"] == wf["gate_mid_n"] == PARAMS.gate_workfunction_n_ev
    assert (wf["gate_bottom"] == wf["gate_mid_p"]
            == PARAMS.gate_workfunction_p_ev)


def test_both_sheets_get_structured_mesh(built, fresh_devsim):
    """Regression: a late geo.synchronize() used to wipe the first sheet's
    transfinite constraints, leaving the pFET with a near-empty mesh."""
    devsim = fresh_devsim
    msh, layout = built
    device = load_mesh(msh, layout, "cfet_t")
    for region in ("silicon_n", "silicon_p"):
        xs = devsim.get_node_model_values(device=device, region=region,
                                          name="x")
        expected = (2 * COARSE.nx_sd + COARSE.nx_gate + 1) * (COARSE.ny_si + 1)
        assert len(xs) == expected, region


def test_coupled_equilibrium_converges(tmp_path, fresh_devsim):
    devsim = fresh_devsim
    msh = tmp_path / "cfet.msh"
    layout = CFETStack2DBuilder(PARAMS, COARSE).build(msh)
    device = load_mesh(msh, layout, PARAMS.name)

    setup_equilibrium(device, layout, PARAMS)

    # each sheet must carry its own doping polarity
    net_n = devsim.get_node_model_values(device=device, region="silicon_n",
                                         name="NetDoping")
    net_p = devsim.get_node_model_values(device=device, region="silicon_p",
                                         name="NetDoping")
    assert max(net_n) > 1e19 and min(net_n) > -2e15  # donor S/D
    assert min(net_p) < -1e19 and max(net_p) < 2e15  # acceptor S/D
    for region in ("silicon_n", "silicon_p"):
        pot = devsim.get_node_model_values(device=device, region=region,
                                           name="Potential")
        assert -0.7 < min(pot) < max(pot) < 0.7
