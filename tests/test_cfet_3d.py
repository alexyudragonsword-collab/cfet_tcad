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


def test_replication_validation():
    with pytest.raises(ValueError, match="only implemented"):
        DeviceParams(structure="gaa_3d", n_fins=2)
    with pytest.raises(ValueError, match="oxide shells overlap"):
        DeviceParams(structure="cfet_3d", n_fins=2, fin_pitch_nm=10.0,
                     sheet_width_nm=18.0)
    with pytest.raises(ValueError, match="oxide shells overlap"):
        DeviceParams(structure="cfet_3d", n_stacked_sheets=2,
                     sheet_pitch_nm=5.0)
    with pytest.raises(ValueError, match=">= 1"):
        DeviceParams(structure="cfet_3d", n_fins=0)


def _drain_current_at_bias(devsim, msh, layout, name):
    """Equilibrium + a small common-gate/drain step; nFET drain current."""
    from cfet_tcad.solve import ramp_biases
    from cfet_tcad.solve.sweep import contact_current

    device = load_mesh(msh, layout, name)
    setup_equilibrium(device, layout,
                      DeviceParams(name=name, structure="cfet_3d"))
    ramp_biases(device, ["drain_n"], 0.3, step=0.1)
    ramp_biases(device, ["gate_n", "gate_p"], 0.3, step=0.1)
    return contact_current(device, "drain_n")


@pytest.mark.slow
@pytest.mark.parametrize("replication", [dict(n_fins=2, fin_pitch_nm=26.0),
                                         dict(n_stacked_sheets=2,
                                              sheet_pitch_nm=15.0)])
def test_replicated_channels_carry_exactly_double_current(
        tmp_path, fresh_devsim, replication):
    """Replicas are disconnected identical copies, so the device current
    must be exactly 2x the single-channel device - this also proves
    DEVSIM handles a region of disconnected components correctly."""
    devsim = fresh_devsim
    single = DeviceParams(name="one", structure="cfet_3d")
    double = DeviceParams(name="two", structure="cfet_3d", **replication)

    msh1 = tmp_path / "one.msh"
    lay1 = CFETStack3DBuilder(single, COARSE).build(msh1)
    i1 = _drain_current_at_bias(devsim, msh1, lay1, "one")

    import cfet_tcad
    cfet_tcad.reset()
    msh2 = tmp_path / "two.msh"
    lay2 = CFETStack3DBuilder(double, COARSE).build(msh2)
    assert set(lay2.regions) == set(lay1.regions)  # contract unchanged
    i2 = _drain_current_at_bias(devsim, msh2, lay2, "two")

    assert i2 == pytest.approx(2.0 * i1, rel=1e-6)


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
