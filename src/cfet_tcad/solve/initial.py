"""Equilibrium setup and solve: nonlinear Poisson first, then coupled DD."""

import devsim

from ..geometry.base import MeshLayout
from ..geometry.params import DeviceParams
from ..physics import equations as eq
from ..physics.doping import create_doping
from ..physics.materials import MATERIALS, SILICON
from ..physics.mobility import create_mobility

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
                      solver_args: dict | None = None) -> None:
    """Assemble physics on all regions and solve the equilibrium state.

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
    for region in silicon_regions:
        mu_n, mu_p = create_mobility(device, region, SILICON, mobility_model)
        eq.create_silicon_dd(device, region, mu_n, mu_p)
    for contact in ohmic_contacts:
        eq.create_ohmic_dd_contact(device, contact)

    devsim.solve(**solver_args)
