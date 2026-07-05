"""Equilibrium setup and solve: nonlinear Poisson first, then coupled DD."""

import devsim

from ..geometry.base import MeshLayout
from ..geometry.params import DeviceParams
from ..physics import equations as eq
from ..physics.doping import create_doping
from ..physics.materials import MATERIALS, SILICON
from ..physics.mobility import create_mobility
from ..physics.quantum import create_density_gradient, create_dg_contact

DEFAULT_SOLVER_ARGS = dict(type="dc", absolute_error=1e10,
                           relative_error=1e-10, maximum_iterations=50)


def enable_extended_precision() -> None:
    """128-bit assembly/solves; markedly improves nanoscale convergence."""
    devsim.set_parameter(name="extended_solver", value=True)
    devsim.set_parameter(name="extended_model", value=True)
    devsim.set_parameter(name="extended_equation", value=True)


def setup_equilibrium(device: str, layout: MeshLayout, params: DeviceParams,
                      *, oxide_material: str = "SiO2",
                      temperature: float = 300.0,
                      taun: float = 1e-7, taup: float = 1e-7,
                      mobility_model: str = "doping_vsat",
                      quantum_model: str = "none",
                      dg_gamma_n: float = 1.0, dg_gamma_p: float = 1.0,
                      solver_args: dict | None = None) -> None:
    """Assemble physics on all regions and solve the equilibrium state.

    With ``quantum_model="density_gradient"`` the classical equilibrium is
    solved first, then the DG quantum potentials are added and the system
    re-solved (with a homotopy on the DG coefficient as fallback).

    After this returns, the device holds a converged drift-diffusion
    solution at zero bias and is ready for bias ramping.
    """
    solver_args = solver_args or DEFAULT_SOLVER_ARGS
    enable_extended_precision()
    oxide = MATERIALS[oxide_material]

    silicon_regions = [r for r, m in layout.regions.items() if m == "Silicon"]
    oxide_regions = [r for r, m in layout.regions.items() if m == "Oxide"]
    gate_contacts = {c: r for c, r in layout.contacts.items()
                     if r in oxide_regions}
    ohmic_contacts = {c: r for c, r in layout.contacts.items()
                      if r in silicon_regions}

    # potential-only system
    for region in silicon_regions:
        eq.set_silicon_parameters(device, region, SILICON, temperature,
                                  taun=taun, taup=taup)
        create_doping(device, region, params)
        eq.create_silicon_potential_only(device, region)
    for region in oxide_regions:
        eq.set_oxide_parameters(device, region, oxide)
        eq.create_oxide_potential_only(device, region)
    for contact, region in ohmic_contacts.items():
        eq.create_ohmic_potential_contact(device, region, contact)
    for contact, region in gate_contacts.items():
        eq.create_gate_contact(device, region, contact,
                               params.gate_workfunction_ev, SILICON)
    for interface in layout.interfaces:
        eq.create_semiconductor_oxide_interface(device, interface)

    devsim.solve(**solver_args)

    # promote to coupled drift-diffusion
    mobilities = {}
    for region in silicon_regions:
        mu_n, mu_p = create_mobility(device, region, SILICON, mobility_model)
        mobilities[region] = (mu_n, mu_p)
        eq.create_silicon_dd(device, region, mu_n, mu_p)
    for contact in ohmic_contacts:
        eq.create_ohmic_dd_contact(device, contact)

    devsim.solve(**solver_args)

    if quantum_model == "density_gradient":
        # transport carrier only: the minority carrier's DG equation is
        # near-singular in the depleted channel and destabilizes Newton
        carriers = ("Electrons",) if params.polarity == "n" else ("Holes",)
        for region in silicon_regions:
            create_density_gradient(device, region, SILICON,
                                    gamma_n=dg_gamma_n, gamma_p=dg_gamma_p,
                                    carriers=carriers)
            eq.apply_quantum_currents(device, region, *mobilities[region],
                                      carriers=carriers)
        for contact in ohmic_contacts:
            create_dg_contact(device, contact, carriers=carriers)
        _solve_dg_with_homotopy(device, solver_args)
    elif quantum_model != "none":
        raise ValueError(f"unknown quantum_model {quantum_model!r}")


def _solve_dg_with_homotopy(device: str, solver_args: dict,
                            min_step: float = 1e-3) -> None:
    """Ramp the DG coefficient from the classical state to full strength.

    Newton does not converge jumping straight from Lambda=0 to the full
    quantum system, so dg_scale climbs a geometric ladder; on a failure the
    step from the last converged scale is bisected (mirroring the adaptive
    bias ramp in solve.sweep)."""
    good = 0.0
    targets = [0.01, 0.03, 0.1, 0.3, 0.6, 1.0]
    while targets:
        scale = targets[0]
        devsim.set_parameter(device=device, name="dg_scale", value=scale)
        try:
            devsim.solve(**solver_args)
            good = scale
            targets.pop(0)
        except devsim.error:
            if scale - good < min_step:
                raise
            targets.insert(0, good + (scale - good) / 2.0)
