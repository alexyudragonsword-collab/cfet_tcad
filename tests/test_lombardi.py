"""Lombardi CVT mobility: element-current parity, convergence, physics."""

import numpy as np
import pytest

from cfet_tcad.geometry import DeviceParams, MeshParams, Nanosheet2DBuilder
from cfet_tcad.meshio_devsim import load_mesh
from cfet_tcad.solve import ramp_biases, setup_equilibrium
from cfet_tcad.solve.sweep import contact_current

PARAMS = DeviceParams(name="cvt_t", gate_workfunction_ev=4.50)
MESH = MeshParams(nx_sd=8, nx_gate=12, ny_si=6, ny_ox=2)


def _bias_to_on(devsim, tmp_path, mobility_model, vd=0.7):
    msh = tmp_path / "dev.msh"
    layout = Nanosheet2DBuilder(PARAMS, MESH).build(msh)
    device = load_mesh(msh, layout, PARAMS.name)
    setup_equilibrium(device, layout, PARAMS, mobility_model=mobility_model)
    ramp_biases(device, ["drain"], vd, step=0.05)
    ramp_biases(device, ["gate_top", "gate_bottom"], 0.7, step=0.05)
    return device


def test_element_current_parity_with_edge_current(tmp_path, fresh_devsim):
    """Rewiring the SG current from edge to element assembly with the SAME
    mobility must reproduce the terminal current bit-for-bit — the
    strongest check that the element machinery integrates correctly."""
    devsim = fresh_devsim
    from devsim.python_packages.model_create import (
        CreateElementModel2d, CreateElementModelDerivative2d)

    device = _bias_to_on(devsim, tmp_path, "doping")
    region = "silicon"
    id_edge = contact_current(device, "drain")

    vdiff = "((Potential@en0 - Potential@en1)/V_t)"
    bern = f"B({vdiff})"
    jn = (f"ElectronCharge*mu_n_lf*EdgeInverseLength*V_t*"
          f"kahan3(Electrons@en1*{bern}, Electrons@en1*{vdiff},"
          f" -Electrons@en0*{bern})")
    jp = (f"-ElectronCharge*mu_p_lf*EdgeInverseLength*V_t*"
          f"kahan3(Holes@en1*{bern}, -Holes@en0*{bern},"
          f" -Holes@en0*{vdiff})")
    for name, expr, var in (("JnE", jn, "Electrons"), ("JpE", jp, "Holes")):
        CreateElementModel2d(device, region, name, expr)
        CreateElementModelDerivative2d(device, region, name, expr,
                                       "Potential", var)
    devsim.equation(device=device, region=region,
                    name="ElectronContinuityEquation",
                    variable_name="Electrons", time_node_model="NCharge",
                    edge_model="", element_model="JnE",
                    node_model="ElectronGeneration",
                    variable_update="positive")
    devsim.equation(device=device, region=region,
                    name="HoleContinuityEquation",
                    variable_name="Holes", time_node_model="PCharge",
                    edge_model="", element_model="JpE",
                    node_model="HoleGeneration", variable_update="positive")
    for c in ("source", "drain"):
        devsim.contact_equation(device=device, contact=c,
                                name="ElectronContinuityEquation",
                                node_model=f"{c}nodeelectrons",
                                element_current_model="JnE")
        devsim.contact_equation(device=device, contact=c,
                                name="HoleContinuityEquation",
                                node_model=f"{c}nodeholes",
                                element_current_model="JpE")
    devsim.solve(type="dc", absolute_error=1e10, relative_error=1e-10,
                 maximum_iterations=30)
    id_elem = contact_current(device, "drain")
    assert id_elem == pytest.approx(id_edge, rel=1e-9)


def test_lombardi_converges_and_degrades_linear_current(tmp_path,
                                                        fresh_devsim):
    """Compare in the linear region (Vd=50mV), where the current is
    mobility-limited; at high Vd velocity saturation masks much of the
    surface-scattering loss in short-channel devices."""
    import cfet_tcad

    device = _bias_to_on(fresh_devsim, tmp_path / "cvt", "lombardi_vsat",
                         vd=0.05)
    id_cvt = abs(contact_current(device, "drain"))
    mu = np.array(fresh_devsim.get_element_model_values(
        device=device, region="silicon", name="mu_n_cvt"))
    assert np.all(mu > 0)
    assert mu.min() < 500.0  # strong surface degradation somewhere

    cfet_tcad.reset()
    device = _bias_to_on(fresh_devsim, tmp_path / "ref", "doping_vsat",
                         vd=0.05)
    id_ref = abs(contact_current(device, "drain"))

    # surface scattering must cost a significant fraction of the
    # mobility-limited linear current
    assert id_cvt < 0.85 * id_ref


def test_lombardi_3d_converges_with_degraded_mobility(tmp_path,
                                                      fresh_devsim):
    """Tetrahedral element assembly: the CVT system must converge on a 3D
    GAA and produce surface-degraded mobility values."""
    from cfet_tcad.geometry import GAANanosheet3DBuilder

    params3 = DeviceParams(name="cvt3d", structure="gaa_3d",
                           gate_workfunction_ev=4.50)
    msh = tmp_path / "gaa.msh"
    layout = GAANanosheet3DBuilder(
        params3, MeshParams(nx_sd=4, nx_gate=6, ny_si=3, ny_ox=2,
                            nz_w=4)).build(msh)
    device = load_mesh(msh, layout, params3.name)
    setup_equilibrium(device, layout, params3,
                      mobility_model="lombardi_vsat")
    mu = np.array(fresh_devsim.get_element_model_values(
        device=device, region="silicon", name="mu_n_cvt"))
    assert np.all(mu > 0)
    assert mu.min() < 800.0  # confinement fields already degrade at Vg=0


def test_full_physics_cvt_plus_dg_converges(tmp_path, fresh_devsim):
    """The Sentaurus-default combination: CVT surface mobility and the
    density-gradient quantum correction together.  Both homotopies must
    reach full strength with both effects present in the solution."""
    devsim = fresh_devsim
    msh = tmp_path / "dev.msh"
    layout = Nanosheet2DBuilder(PARAMS, MESH).build(msh)
    device = load_mesh(msh, layout, PARAMS.name)
    setup_equilibrium(device, layout, PARAMS,
                      mobility_model="lombardi_vsat",
                      quantum_model="density_gradient")
    assert devsim.get_parameter(device=device, name="cvt_scale") == 1.0
    assert devsim.get_parameter(device=device, name="dg_scale") == 1.0

    ramp_biases(device, ["drain"], 0.05, step=0.05)
    ramp_biases(device, ["gate_top", "gate_bottom"], 0.7, step=0.05)

    lam = np.array(devsim.get_node_model_values(
        device=device, region="silicon", name="Lambda_n"))
    mu = np.array(devsim.get_element_model_values(
        device=device, region="silicon", name="mu_n_cvt"))
    assert np.abs(lam).max() > 5e-3      # quantum potential active
    assert mu.min() < 500.0              # surface degradation active
    assert abs(contact_current(device, "drain")) > 0
