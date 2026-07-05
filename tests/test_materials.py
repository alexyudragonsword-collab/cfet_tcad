"""Heteromaterial support: SiGe channel selection and its physics effect."""

import pytest

from cfet_tcad.geometry import CFETStack2DBuilder, DeviceParams, MeshParams
from cfet_tcad.meshio_devsim import load_mesh
from cfet_tcad.physics.materials import MATERIALS, SIGE30, SILICON
from cfet_tcad.solve import ramp_biases, setup_equilibrium
from cfet_tcad.solve.sweep import contact_current

MESH = MeshParams(nx_sd=8, nx_gate=12, ny_si=6, ny_ox=2)


def test_sige_material_entry():
    assert MATERIALS["SiGe30"] is SIGE30
    assert SIGE30.eg_ev < SILICON.eg_ev
    assert SIGE30.n_i > SILICON.n_i
    assert SIGE30.mu_max_p > SILICON.mu_max_p  # strain-enhanced holes


def test_sige_factory_interpolation():
    from cfet_tcad.physics.materials import get_material, sige

    # anchors: x=0 reproduces Silicon, x=0.30 the SiGe30 entry
    s0 = sige(0.0)
    for attr in ("eg_ev", "n_i", "eps_r", "mu_max_p", "mu_min_p",
                 "mu_max_n", "mu_min_n"):
        assert getattr(s0, attr) == pytest.approx(getattr(SILICON, attr),
                                                  rel=1e-9)
    assert sige(0.30).eg_ev == pytest.approx(SIGE30.eg_ev)
    assert sige(0.30).mu_max_p == pytest.approx(SIGE30.mu_max_p)

    # monotone composition dependence
    assert sige(0.45).mu_max_p > sige(0.15).mu_max_p
    assert sige(0.45).eg_ev < sige(0.15).eg_ev

    # dynamic key resolution
    assert get_material("SiGe15").eg_ev == pytest.approx(sige(0.15).eg_ev)
    assert get_material("Silicon") is SILICON
    with pytest.raises(ValueError, match="unknown material"):
        get_material("Diamond")
    with pytest.raises(ValueError, match="Ge fraction"):
        get_material("SiGe75")  # beyond the strained-on-Si range


def test_layout_carries_per_sheet_materials(tmp_path):
    params = DeviceParams(name="mat_t", structure="cfet_2d",
                          channel_material_p="SiGe30")
    layout = CFETStack2DBuilder(params, MESH).build(tmp_path / "m.msh")
    assert layout.semiconductor_materials == {"silicon_n": "Silicon",
                                              "silicon_p": "SiGe30"}
    assert layout.gate_semiconductors["gate_mid_p"] == "silicon_p"
    assert layout.gate_semiconductors["gate_top"] == "silicon_n"


def test_unknown_material_rejected(tmp_path, fresh_devsim):
    params = DeviceParams(name="mat_bad", channel_material="Unobtainium")
    from cfet_tcad.geometry import Nanosheet2DBuilder
    msh = tmp_path / "m.msh"
    layout = Nanosheet2DBuilder(params, MESH).build(msh)
    device = load_mesh(msh, layout, params.name)
    with pytest.raises(ValueError, match="Unobtainium"):
        setup_equilibrium(device, layout, params)


def _pfet_on_current(devsim, tmp_path, material):
    params = DeviceParams(name="mat_cfet", structure="cfet_2d",
                          channel_material_p=material)
    msh = tmp_path / "m.msh"
    layout = CFETStack2DBuilder(params, MESH).build(msh)
    device = load_mesh(msh, layout, params.name)
    setup_equilibrium(device, layout, params)
    # pFET linear region, fully on
    ramp_biases(device, ["drain_p"], -0.05, step=0.05)
    ramp_biases(device, ["gate_bottom", "gate_mid_p", "gate_mid_n",
                         "gate_top"], -0.7, step=0.05)
    return abs(contact_current(device, "drain_p"))


def test_sige_pfet_boosts_drive(tmp_path, fresh_devsim):
    import cfet_tcad

    id_si = _pfet_on_current(fresh_devsim, tmp_path / "si", "Silicon")
    cfet_tcad.reset()
    id_sige = _pfet_on_current(fresh_devsim, tmp_path / "sige", "SiGe30")
    # strained SiGe hole mobility must translate into more linear drive
    assert id_sige > 1.3 * id_si
