"""Inverter VTC: FOM extraction on synthetic data and the mixed
device/circuit equilibrium of the CFET stack."""

import numpy as np
import pytest

from cfet_tcad.extract import extract_vtc_fom
from cfet_tcad.geometry import CFETStack2DBuilder, DeviceParams, MeshParams
from cfet_tcad.meshio_devsim import load_mesh
from cfet_tcad.solve import ramp_biases, setup_equilibrium


def synthetic_vtc(vdd=0.7, vm=0.35, steepness=30.0):
    vin = np.linspace(0.0, vdd, 57)
    vout = vdd / (1.0 + np.exp(steepness * (vin - vm)))
    return vin, vout


def test_vtc_fom_on_synthetic_curve():
    vdd, vm = 0.7, 0.35
    vin, vout = synthetic_vtc(vdd=vdd, vm=vm)
    fom = extract_vtc_fom(vin, vout, vdd)
    assert fom["vm_v"] == pytest.approx(vm, abs=0.01)
    # logistic: max gain = steepness*vdd/4
    assert fom["max_gain"] == pytest.approx(30.0 * vdd / 4.0, rel=0.1)
    assert fom["voh_v"] == pytest.approx(vdd, abs=0.01)
    assert fom["vol_v"] == pytest.approx(0.0, abs=0.01)
    assert 0.0 < fom["nml_v"] < vdd
    assert 0.0 < fom["nmh_v"] < vdd
    assert fom["vil_v"] < fom["vm_v"] < fom["vih_v"]


def test_cfet_circuit_equilibrium_and_pullup(tmp_path, fresh_devsim):
    """With the drains on the floating vout node, equilibrium must solve,
    and raising the pFET source to Vdd at Vin=0 must pull vout to ~Vdd."""
    devsim = fresh_devsim
    params = DeviceParams(name="vtc_t", structure="cfet_2d")
    mesh = MeshParams(nx_sd=8, nx_gate=12, ny_si=6, ny_ox=2)
    msh = tmp_path / "cfet.msh"
    layout = CFETStack2DBuilder(params, mesh).build(msh)
    device = load_mesh(msh, layout, params.name)

    devsim.circuit_element(name="R1", n1="vout", n2="0", value=1.0e15)
    setup_equilibrium(device, layout, params,
                      circuit_contacts={"drain_n": "vout",
                                        "drain_p": "vout"})
    assert abs(devsim.get_circuit_node_value(node="vout")) < 1e-3

    vdd = 0.7
    ramp_biases(device, ["source_p"], vdd, step=0.05)
    vout = devsim.get_circuit_node_value(node="vout")
    assert vout == pytest.approx(vdd, abs=0.02)  # pFET on, output high
