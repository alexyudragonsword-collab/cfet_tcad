"""3D CFET stack: layout contract, DEVSIM import, coupled equilibrium."""

import pytest

from cfet_tcad.geometry import CFETStack3DBuilder, DeviceParams, MeshParams
from cfet_tcad.meshio_devsim import load_mesh
from cfet_tcad.solve import setup_equilibrium

PARAMS = DeviceParams(name="cfet3d_t", structure="cfet_3d")
COARSE = MeshParams(nx_sd=4, nx_gate=6, ny_si=3, ny_ox=2, nz_w=4)


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    msh = tmp_path_factory.mktemp("cfet3d") / "cfet.msh"
    layout = CFETStack3DBuilder(PARAMS, COARSE).build(msh)
    return msh, layout


def test_layout_contract_3d(built):
    _, layout = built
    assert layout.dimension == 3
    assert set(layout.regions) == {"silicon_n", "silicon_p",
                                   "oxide_n", "oxide_p"}
    assert set(layout.contacts) == {"source_n", "drain_n", "gate_n",
                                    "source_p", "drain_p", "gate_p"}
    assert layout.silicon_polarity == {"silicon_n": "n", "silicon_p": "p"}
    assert layout.gate_workfunctions == {
        "gate_n": PARAMS.gate_workfunction_n_ev,
        "gate_p": PARAMS.gate_workfunction_p_ev}
    assert layout.interfaces == {"si_ox_n": ("silicon_n", "oxide_n"),
                                 "si_ox_p": ("silicon_p", "oxide_p")}


def test_sheets_are_vertically_separated(built, fresh_devsim):
    devsim = fresh_devsim
    msh, layout = built
    device = load_mesh(msh, layout, "cfet3d_t")
    y_p = devsim.get_node_model_values(device=device, region="silicon_p",
                                       name="y")
    y_n = devsim.get_node_model_values(device=device, region="silicon_n",
                                       name="y")
    gap = min(y_n) - max(y_p)
    # separated by two oxide thicknesses plus the metal gap
    expected = 2 * PARAMS.t_ox + PARAMS.t_gap_nm * 1e-7
    assert gap == pytest.approx(expected, rel=1e-6)


def test_coupled_equilibrium_converges_3d(tmp_path, fresh_devsim):
    devsim = fresh_devsim
    msh = tmp_path / "cfet.msh"
    layout = CFETStack3DBuilder(PARAMS, COARSE).build(msh)
    device = load_mesh(msh, layout, PARAMS.name)

    setup_equilibrium(device, layout, PARAMS)

    net_n = devsim.get_node_model_values(device=device, region="silicon_n",
                                         name="NetDoping")
    net_p = devsim.get_node_model_values(device=device, region="silicon_p",
                                         name="NetDoping")
    assert max(net_n) > 1e19    # donor S/D on the nFET sheet
    assert min(net_p) < -1e19   # acceptor S/D on the pFET sheet
    for region in ("silicon_n", "silicon_p"):
        pot = devsim.get_node_model_values(device=device, region=region,
                                           name="Potential")
        assert -0.7 < min(pot) < max(pot) < 0.7
