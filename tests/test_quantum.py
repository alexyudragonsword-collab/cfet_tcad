"""Density-gradient quantum correction: convergence and physical effect."""

import numpy as np
import pytest

from cfet_tcad.geometry import DeviceParams, MeshParams, Nanosheet2DBuilder
from cfet_tcad.meshio_devsim import load_mesh
from cfet_tcad.physics.quantum import dg_coefficient
from cfet_tcad.solve import setup_equilibrium

PARAMS = DeviceParams(name="dg_t", gate_workfunction_ev=4.50)
MESH = MeshParams(nx_sd=8, nx_gate=12, ny_si=8, ny_ox=2)


def _equilibrium_electrons(devsim, tmp_path, quantum_model):
    msh = tmp_path / "dev.msh"
    layout = Nanosheet2DBuilder(PARAMS, MESH).build(msh)
    device = load_mesh(msh, layout, PARAMS.name)
    setup_equilibrium(device, layout, PARAMS, quantum_model=quantum_model)
    get = lambda name: np.array(devsim.get_node_model_values(  # noqa: E731
        device=device, region="silicon", name=name))
    return get


def test_dg_coefficient_magnitude():
    # b = hbar^2/(12 q m0 m*) with m*=0.3 is ~2.1e-16 V cm^2
    assert dg_coefficient(0.3) == pytest.approx(2.12e-16, rel=0.05)
    assert dg_coefficient(0.3, gamma=2.0) == pytest.approx(4.23e-16, rel=0.05)


def test_dg_equilibrium_converges_with_nontrivial_lambda(tmp_path,
                                                         fresh_devsim):
    get = _equilibrium_electrons(fresh_devsim, tmp_path, "density_gradient")
    lam = get("Lambda_n")
    # the quantum potential must be a non-trivial field of ~10s of mV
    assert np.abs(lam).max() > 5e-3
    assert np.abs(lam).max() < 0.5
    assert np.all(np.isfinite(lam))
    assert np.all(get("Electrons") > 0)


def test_dg_volume_inversion_vs_classical(tmp_path, fresh_devsim):
    """The oxide-barrier Robin condition must push carriers away from the
    Si/SiO2 interfaces: the interface-to-center density ratio drops
    relative to the classical solution (volume inversion)."""
    import cfet_tcad

    get_c = _equilibrium_electrons(fresh_devsim, tmp_path / "c", "none")
    x, y, n_c = get_c("x"), get_c("y"), get_c("Electrons")

    cfet_tcad.reset()
    get_q = _equilibrium_electrons(fresh_devsim, tmp_path / "q",
                                   "density_gradient")
    n_q = get_q("Electrons")

    # mid-channel column: x closest to L/2
    xmid = PARAMS.l_total / 2.0
    col = np.abs(x - x[np.argmin(np.abs(x - xmid))]) < 1e-12
    iface = col & ((np.abs(y) < 1e-12) | (np.abs(y - PARAMS.t_si) < 1e-12))
    center = col & (np.abs(y - PARAMS.t_si / 2)
                    < PARAMS.t_si / (2 * MESH.ny_si))
    ratio_c = n_c[iface].mean() / n_c[center].mean()
    ratio_q = n_q[iface].mean() / n_q[center].mean()
    assert ratio_q < ratio_c
    assert ratio_q < 1.0  # DG peak sits in the body, not at the interface


def test_unknown_quantum_model_rejected(tmp_path, fresh_devsim):
    msh = tmp_path / "dev.msh"
    layout = Nanosheet2DBuilder(PARAMS, MESH).build(msh)
    device = load_mesh(msh, layout, PARAMS.name)
    with pytest.raises(ValueError, match="quantum_model"):
        setup_equilibrium(device, layout, PARAMS, quantum_model="qm_magic")
