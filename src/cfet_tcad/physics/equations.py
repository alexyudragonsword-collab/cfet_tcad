"""DEVSIM equation assembly: nonlinear Poisson and drift-diffusion.

Adapted from devsim.python_packages.simple_physics with two extensions:
- pluggable mobility expressions (doping-dependent + velocity saturation)
  inlined into the Scharfetter-Gummel currents so DEVSIM's model-aware
  symbolic diff() produces exact Newton derivatives;
- metal gate contacts with a configurable workfunction offset.

Solution sequence per region: create the potential-only (nonlinear Poisson)
system first, solve it, then promote to the coupled drift-diffusion system
(:func:`create_silicon_dd` replaces the Poisson charge term).

Phase 2 hook: a density-gradient quantum correction would add a generalized
potential to the carrier models created here; see ``create_silicon_dd``.
"""

import devsim
from devsim.python_packages.model_create import (
    CreateContactNodeModel,
    CreateEdgeModel,
    CreateEdgeModelDerivatives,
    CreateNodeModel,
    CreateNodeModelDerivative,
    CreateContinuousInterfaceModel,
    CreateSolution,
    InEdgeModelList,
    InNodeModelList,
)

from .materials import EPS_0, K_B, Q, InsulatorParams, SemiconductorParams

ECE_NAME = "ElectronContinuityEquation"
HCE_NAME = "HoleContinuityEquation"

# equilibrium carrier densities at an ohmic contact
CELEC = "(1e-10 + 0.5*abs(NetDoping + (NetDoping^2 + 4*n_i^2)^(0.5)))"
CHOLE = "(1e-10 + 0.5*abs(-NetDoping + (NetDoping^2 + 4*n_i^2)^(0.5)))"


def contact_bias_name(contact: str) -> str:
    return f"{contact}_bias"


# --- parameters ---------------------------------------------------------

def set_silicon_parameters(device: str, region: str,
                           mat: SemiconductorParams, temperature: float,
                           taun: float = 1e-7, taup: float = 1e-7) -> None:
    p = devsim.set_parameter
    p(device=device, region=region, name="Permittivity", value=mat.eps_r * EPS_0)
    p(device=device, region=region, name="ElectronCharge", value=Q)
    p(device=device, region=region, name="n_i", value=mat.n_i)
    p(device=device, region=region, name="T", value=temperature)
    p(device=device, region=region, name="kT", value=K_B * temperature)
    p(device=device, region=region, name="V_t", value=K_B * temperature / Q)
    # constant-mobility fallbacks (mobility model may override in currents)
    p(device=device, region=region, name="mu_n", value=400.0)
    p(device=device, region=region, name="mu_p", value=200.0)
    # SRH
    p(device=device, region=region, name="n1", value=mat.n_i)
    p(device=device, region=region, name="p1", value=mat.n_i)
    p(device=device, region=region, name="taun", value=taun)
    p(device=device, region=region, name="taup", value=taup)


def set_oxide_parameters(device: str, region: str,
                         mat: InsulatorParams) -> None:
    devsim.set_parameter(device=device, region=region, name="Permittivity",
                         value=mat.eps_r * EPS_0)
    devsim.set_parameter(device=device, region=region, name="ElectronCharge",
                         value=Q)


# --- potential-only (nonlinear Poisson) ---------------------------------

def create_silicon_potential_only(device: str, region: str) -> None:
    if not InNodeModelList(device, region, "Potential"):
        CreateSolution(device, region, "Potential")
        # charge-neutral initial guess: exact equilibrium potential far from
        # junctions, which keeps Newton in the convergence basin at nm scale
        neutral = (f"ifelse(NetDoping > 0, V_t*log({CELEC}/n_i),"
                   f" -V_t*log({CHOLE}/n_i))")
        CreateNodeModel(device, region, "NeutralPotential", neutral)
        devsim.set_node_values(device=device, region=region,
                               name="Potential",
                               init_from="NeutralPotential")

    intrinsics = (
        ("IntrinsicElectrons", "n_i*exp(Potential/V_t)"),
        ("IntrinsicHoles", "n_i^2/IntrinsicElectrons"),
        ("IntrinsicCharge",
         "kahan3(IntrinsicHoles, -IntrinsicElectrons, NetDoping)"),
        ("PotentialIntrinsicCharge", "-ElectronCharge * IntrinsicCharge"),
    )
    for name, eq in intrinsics:
        CreateNodeModel(device, region, name, eq)
        CreateNodeModelDerivative(device, region, name, eq, "Potential")

    for name, eq in (
        ("ElectricField", "(Potential@n0 - Potential@n1)*EdgeInverseLength"),
        ("PotentialEdgeFlux", "Permittivity * ElectricField"),
    ):
        CreateEdgeModel(device, region, name, eq)
        CreateEdgeModelDerivatives(device, region, name, eq, "Potential")

    devsim.equation(device=device, region=region, name="PotentialEquation",
                    variable_name="Potential",
                    node_model="PotentialIntrinsicCharge",
                    edge_model="PotentialEdgeFlux",
                    variable_update="log_damp")


def create_oxide_potential_only(device: str, region: str) -> None:
    if not InNodeModelList(device, region, "Potential"):
        CreateSolution(device, region, "Potential")
    efield = "(Potential@n0 - Potential@n1)*EdgeInverseLength"
    CreateEdgeModel(device, region, "ElectricField", efield)
    CreateEdgeModelDerivatives(device, region, "ElectricField", efield,
                               "Potential")
    dfield = "Permittivity*ElectricField"
    CreateEdgeModel(device, region, "PotentialEdgeFlux", dfield)
    CreateEdgeModelDerivatives(device, region, "PotentialEdgeFlux", dfield,
                               "Potential")
    devsim.equation(device=device, region=region, name="PotentialEquation",
                    variable_name="Potential",
                    edge_model="PotentialEdgeFlux",
                    variable_update="default")


# --- contacts ------------------------------------------------------------

def _ensure_contact_charge_edge(device: str, region: str) -> None:
    if not InEdgeModelList(device, region, "contactcharge_edge"):
        CreateEdgeModel(device, region, "contactcharge_edge",
                        "Permittivity*ElectricField")
        CreateEdgeModelDerivatives(device, region, "contactcharge_edge",
                                   "Permittivity*ElectricField", "Potential")


def create_ohmic_potential_contact(device: str, region: str, contact: str,
                                   circuit_node: str | None = None) -> None:
    """Ohmic contact (source/drain): pins Potential to bias + built-in.

    With ``circuit_node`` the boundary voltage is a circuit unknown instead
    of a parameter, coupling the contact into DEVSIM's mixed device/circuit
    Newton system (the node must already exist via a circuit_element).
    """
    _ensure_contact_charge_edge(device, region)
    if circuit_node is None:
        bias = contact_bias_name(contact)
        devsim.set_parameter(device=device, name=bias, value=0.0)
    else:
        bias = circuit_node
    model = (f"Potential - {bias} + ifelse(NetDoping > 0,"
             f" -V_t*log({CELEC}/n_i), V_t*log({CHOLE}/n_i))")
    name = f"{contact}nodemodel"
    CreateContactNodeModel(device, contact, name, model)
    CreateContactNodeModel(device, contact, f"{name}:Potential", "1")
    if circuit_node is None:
        devsim.contact_equation(device=device, contact=contact,
                                name="PotentialEquation",
                                node_model=name,
                                edge_charge_model="contactcharge_edge")
    else:
        CreateContactNodeModel(device, contact, f"{name}:{bias}", "-1")
        devsim.contact_equation(device=device, contact=contact,
                                name="PotentialEquation",
                                node_model=name,
                                edge_charge_model="contactcharge_edge",
                                circuit_node=circuit_node)


def create_gate_contact(device: str, region: str, contact: str,
                        workfunction_ev: float,
                        semiconductor: SemiconductorParams) -> None:
    """Metal gate on oxide.

    Potential is referenced to the silicon intrinsic Fermi level, so the
    gate boundary condition is  Potential = bias - (WF - WF_midgap).
    """
    _ensure_contact_charge_edge(device, region)
    bias = contact_bias_name(contact)
    offset = workfunction_ev - semiconductor.midgap_workfunction_ev
    devsim.set_parameter(device=device, name=bias, value=0.0)
    devsim.set_parameter(device=device, name=f"{contact}_wf_offset",
                         value=offset)
    model = f"Potential - {bias} + {contact}_wf_offset"
    name = f"{contact}nodemodel"
    CreateContactNodeModel(device, contact, name, model)
    CreateContactNodeModel(device, contact, f"{name}:Potential", "1")
    devsim.contact_equation(device=device, contact=contact,
                            name="PotentialEquation",
                            node_model=name,
                            edge_charge_model="contactcharge_edge")


def create_ohmic_dd_contact(device: str, contact: str,
                            circuit_node: str | None = None) -> None:
    """Pin carriers to their equilibrium values; integrate contact current.

    With ``circuit_node`` the electron/hole contact currents are injected
    into that circuit node's KCL equation."""
    elec = f"Electrons - ifelse(NetDoping > 0, {CELEC}, n_i^2/{CHOLE})"
    hole = f"Holes - ifelse(NetDoping < 0, {CHOLE}, n_i^2/{CELEC})"
    ename = f"{contact}nodeelectrons"
    hname = f"{contact}nodeholes"
    CreateContactNodeModel(device, contact, ename, elec)
    CreateContactNodeModel(device, contact, f"{ename}:Electrons", "1")
    CreateContactNodeModel(device, contact, hname, hole)
    CreateContactNodeModel(device, contact, f"{hname}:Holes", "1")
    extra = {} if circuit_node is None else {"circuit_node": circuit_node}
    devsim.contact_equation(device=device, contact=contact, name=ECE_NAME,
                            node_model=ename,
                            edge_current_model="ElectronCurrent", **extra)
    devsim.contact_equation(device=device, contact=contact, name=HCE_NAME,
                            node_model=hname,
                            edge_current_model="HoleCurrent", **extra)


# --- drift-diffusion -----------------------------------------------------

def _create_bernoulli(device: str, region: str) -> None:
    CreateEdgeModel(device, region, "vdiff",
                    "(Potential@n0 - Potential@n1)/V_t")
    CreateEdgeModel(device, region, "vdiff:Potential@n0", "V_t^(-1)")
    CreateEdgeModel(device, region, "vdiff:Potential@n1",
                    "-vdiff:Potential@n0")
    CreateEdgeModel(device, region, "Bern01", "B(vdiff)")
    CreateEdgeModel(device, region, "Bern01:Potential@n0",
                    "dBdx(vdiff) * vdiff:Potential@n0")
    CreateEdgeModel(device, region, "Bern01:Potential@n1",
                    "-Bern01:Potential@n0")


_QUANTUM_BERNOULLI = {"Electrons": ("n", "Lambda_n", "-"),
                      "Holes": ("p", "Lambda_p", "+")}


def _create_quantum_bernoulli(device: str, region: str,
                              carriers: tuple) -> None:
    """Per-carrier Bernoulli models on the DG effective potentials
    (electrons: Potential - Lambda_n; holes: Potential + Lambda_p)."""
    for suffix, lam, sign in (_QUANTUM_BERNOULLI[c] for c in carriers):
        v = f"vdiff_{suffix}"
        b = f"Bern01_{suffix}"
        CreateEdgeModel(device, region, v,
                        f"((Potential@n0 {sign} {lam}@n0)"
                        f" - (Potential@n1 {sign} {lam}@n1))/V_t")
        CreateEdgeModel(device, region, f"{v}:Potential@n0", "V_t^(-1)")
        CreateEdgeModel(device, region, f"{v}:Potential@n1",
                        f"-{v}:Potential@n0")
        CreateEdgeModel(device, region, f"{v}:{lam}@n0",
                        f"{sign}V_t^(-1)")
        CreateEdgeModel(device, region, f"{v}:{lam}@n1",
                        f"-{v}:{lam}@n0")
        CreateEdgeModel(device, region, b, f"B({v})")
        for var in ("Potential", lam):
            CreateEdgeModel(device, region, f"{b}:{var}@n0",
                            f"dBdx({v}) * {v}:{var}@n0")
            CreateEdgeModel(device, region, f"{b}:{var}@n1",
                            f"-{b}:{var}@n0")


def _create_srh(device: str, region: str) -> None:
    usrh = ("(Electrons*Holes - n_i^2)"
            "/(taup*(Electrons + n1) + taun*(Holes + p1))")
    gn = "-ElectronCharge * USRH"
    gp = "+ElectronCharge * USRH"
    CreateNodeModel(device, region, "USRH", usrh)
    CreateNodeModel(device, region, "ElectronGeneration", gn)
    CreateNodeModel(device, region, "HoleGeneration", gp)
    for var in ("Electrons", "Holes"):
        CreateNodeModelDerivative(device, region, "USRH", usrh, var)
        CreateNodeModelDerivative(device, region, "ElectronGeneration", gn, var)
        CreateNodeModelDerivative(device, region, "HoleGeneration", gp, var)


def _create_sg_currents(device: str, region: str,
                        mu_n_expr: str, mu_p_expr: str,
                        quantum_carriers: tuple = ()) -> None:
    """Scharfetter-Gummel edge currents.  Carriers named in
    ``quantum_carriers`` use the Bernoulli models of their DG effective
    potential and gain the quantum potential in their derivative sets."""
    q_n = "Electrons" in quantum_carriers
    q_p = "Holes" in quantum_carriers
    bn, vn = ("Bern01_n", "vdiff_n") if q_n else ("Bern01", "vdiff")
    bp, vp = ("Bern01_p", "vdiff_p") if q_p else ("Bern01", "vdiff")
    n_vars = ("Potential", "Electrons", "Holes") + (
        ("Lambda_n",) if q_n else ())
    p_vars = ("Potential", "Electrons", "Holes") + (
        ("Lambda_p",) if q_p else ())

    jn = (f"ElectronCharge*{mu_n_expr}*EdgeInverseLength*V_t*"
          f"kahan3(Electrons@n1*{bn}, Electrons@n1*{vn},"
          f" -Electrons@n0*{bn})")
    CreateEdgeModel(device, region, "ElectronCurrent", jn)
    for var in n_vars:
        CreateEdgeModelDerivatives(device, region, "ElectronCurrent", jn, var)

    jp = (f"-ElectronCharge*{mu_p_expr}*EdgeInverseLength*V_t*"
          f"kahan3(Holes@n1*{bp}, -Holes@n0*{bp}, -Holes@n0*{vp})")
    CreateEdgeModel(device, region, "HoleCurrent", jp)
    for var in p_vars:
        CreateEdgeModelDerivatives(device, region, "HoleCurrent", jp, var)


def apply_quantum_currents(device: str, region: str,
                           mu_n_expr: str, mu_p_expr: str,
                           carriers: tuple = ("Electrons", "Holes")) -> None:
    """Switch the SG currents of ``carriers`` onto their DG effective
    potentials.

    Call after create_density_gradient (Lambda solutions must exist).
    The continuity and contact equations reference the currents by name,
    so replacing the edge models rewires the whole system in place.
    """
    _create_quantum_bernoulli(device, region, carriers)
    _create_sg_currents(device, region, mu_n_expr, mu_p_expr,
                        quantum_carriers=carriers)


def create_silicon_dd(device: str, region: str,
                      mu_n_expr: str = "mu_n",
                      mu_p_expr: str = "mu_p") -> None:
    """Promote a potential-only silicon region to coupled drift-diffusion.

    ``mu_n_expr`` / ``mu_p_expr`` are expression strings from
    :func:`cfet_tcad.physics.mobility.create_mobility`, inlined into the
    Scharfetter-Gummel currents.  diff() resolves named sub-models through
    their ``model:variable`` derivative models (Bern01, vdiff) and treats
    derivative-free models (mu_*_lf) as constants, so Newton derivatives
    stay exact for the field-dependent parts written inline.
    """
    for carrier in ("Electrons", "Holes"):
        if not InNodeModelList(device, region, carrier):
            CreateSolution(device, region, carrier)
            devsim.set_node_values(
                device=device, region=region, name=carrier,
                init_from="IntrinsicElectrons" if carrier == "Electrons"
                else "IntrinsicHoles")

    # Poisson with solved carriers
    pne = "-ElectronCharge*kahan3(Holes, -Electrons, NetDoping)"
    CreateNodeModel(device, region, "PotentialNodeCharge", pne)
    CreateNodeModelDerivative(device, region, "PotentialNodeCharge", pne,
                              "Electrons", "Holes")
    devsim.equation(device=device, region=region, name="PotentialEquation",
                    variable_name="Potential",
                    node_model="PotentialNodeCharge",
                    edge_model="PotentialEdgeFlux",
                    variable_update="log_damp")

    _create_bernoulli(device, region)
    _create_srh(device, region)
    _create_sg_currents(device, region, mu_n_expr, mu_p_expr)

    ncharge = "-ElectronCharge * Electrons"
    CreateNodeModel(device, region, "NCharge", ncharge)
    CreateNodeModelDerivative(device, region, "NCharge", ncharge, "Electrons")
    devsim.equation(device=device, region=region, name=ECE_NAME,
                    variable_name="Electrons",
                    time_node_model="NCharge",
                    edge_model="ElectronCurrent",
                    node_model="ElectronGeneration",
                    variable_update="positive")

    pcharge = "ElectronCharge * Holes"
    CreateNodeModel(device, region, "PCharge", pcharge)
    CreateNodeModelDerivative(device, region, "PCharge", pcharge, "Holes")
    devsim.equation(device=device, region=region, name=HCE_NAME,
                    variable_name="Holes",
                    time_node_model="PCharge",
                    edge_model="HoleCurrent",
                    node_model="HoleGeneration",
                    variable_update="positive")


# --- interfaces -----------------------------------------------------------

def create_semiconductor_oxide_interface(device: str, interface: str) -> None:
    model = CreateContinuousInterfaceModel(device, interface, "Potential")
    devsim.interface_equation(device=device, interface=interface,
                              name="PotentialEquation",
                              interface_model=model, type="continuous")
