"""Density-gradient (Bohm quantum potential) correction.

Adds one quantum-potential solution variable per carrier on semiconductor
regions and couples it into the Newton system:

    n = n_i exp((psi - Lambda_n - phi_n)/V_t)
    Lambda_n = -2 b_n grad^2(sqrt(n)) / sqrt(n)
    b_n = gamma_n hbar^2 / (12 q m0 m_dg_n)      (holes symmetric, psi+Lambda_p)

Assembled in the symmetrized flux form (multiply through by sqrt(n) to
avoid dividing by a vanishing density):

    integral(Lambda_n*sqrt(n)) + surface_integral(2 b_n grad(sqrt(n))) = 0

which maps onto DEVSIM's equation convention as
    node model: Lambda_n * sqrt(Electrons)
    edge model: dg_scale * 2 b_n (sqrt(n)@n1 - sqrt(n)@n0) * EdgeInverseLength

``dg_scale`` is a homotopy knob (0 -> classical, 1 -> full correction) used
by the solver when direct convergence fails.

Boundary conditions: Lambda = 0 on ohmic contacts.  At semiconductor/
insulator interfaces a Robin condition models wavefunction decay into the
oxide barrier,

    grad(sqrt(n)) . n_out = -sqrt(n)/d_pen,   d_pen = hbar/sqrt(2 m_ox dEc)

(~0.16 nm for Si/SiO2 electrons).  It enters the weak form as a surface
term assembled with DEVSIM's SurfaceArea/NodeVolume node models; this is
what produces the interface carrier exclusion (volume inversion, positive
Vt shift).  Without it, the only DG effect is longitudinal barrier
smoothing, which *raises* leakage.
"""

import devsim
from devsim.python_packages.model_create import (
    CreateContactNodeModel,
    CreateEdgeModel,
    CreateEdgeModelDerivatives,
    CreateNodeModel,
    CreateNodeModelDerivative,
    CreateSolution,
    InEdgeModelList,
)

from .materials import HBAR, M0, Q, SemiconductorParams

#: (carrier variable, quantum potential variable, b parameter, d_pen parameter)
DG_CARRIERS = (("Electrons", "Lambda_n", "b_dg_n", "d_pen_n"),
               ("Holes", "Lambda_p", "b_dg_p", "d_pen_p"))

# oxide penetration depths hbar/sqrt(2 m_ox dE) for Si/SiO2 [cm]
D_PEN_N = 1.6e-8   # dEc ~ 3.1 eV, m_ox ~ 0.5 m0
D_PEN_P = 1.2e-8   # dEv ~ 4.5 eV, m_ox ~ 0.6 m0

# DG direction weights: quantum correction acts along the confinement
# directions (y across the sheet, z across its width) but is switched off
# along transport (x) — the standard TCAD practice (cf. Sentaurus
# anisotropic eQuantumPotential); an isotropic DG spuriously smooths the
# source-drain barrier at short Lg, raising Ioff and SS.
DG_ANISO = {"x": 0.0, "y": 1.0, "z": 1.0}


def dg_coefficient(mass_fraction: float, gamma: float = 1.0) -> float:
    """b = gamma hbar^2/(12 q m0 m*) in V cm^2."""
    b_si = gamma * HBAR ** 2 / (12.0 * Q * M0 * mass_fraction)  # V m^2
    return b_si * 1.0e4


def create_density_gradient(device: str, region: str,
                            mat: SemiconductorParams,
                            gamma_n: float = 1.0,
                            gamma_p: float = 1.0,
                            carriers: tuple = ("Electrons", "Holes")) -> None:
    """Create the quantum-potential solutions and DG equations for
    ``carriers``.

    Requires the Electrons/Holes solutions (call after the classical DD
    system is assembled).  Lambda fields start at 0 == classical limit.

    Apply DG to the transport carrier only (electrons in an nFET, holes in
    a pFET): the minority carrier is depleted to near-zero density in the
    channel, where its DG equation is close to singular and destabilizes
    Newton while contributing nothing physical.
    """
    devsim.set_parameter(device=device, region=region, name="b_dg_n",
                         value=dg_coefficient(mat.m_dg_n, gamma_n))
    devsim.set_parameter(device=device, region=region, name="b_dg_p",
                         value=dg_coefficient(mat.m_dg_p, gamma_p))
    devsim.set_parameter(device=device, region=region, name="d_pen_n",
                         value=D_PEN_N)
    devsim.set_parameter(device=device, region=region, name="d_pen_p",
                         value=D_PEN_P)
    devsim.set_parameter(device=device, name="dg_scale", value=1.0)

    for carrier, lam, b, dpen in DG_CARRIERS:
        if carrier not in carriers:
            continue
        CreateSolution(device, region, lam)

        # sqrt regularized with +1 cm^-3: physically negligible against any
        # relevant density, but bounds d(sqrt(n))/dn as the Robin term
        # drives the interface density toward zero (else Newton diverges
        # on the first bias step regardless of step size)
        u = f"(({carrier} + 1)^(0.5))"
        # volume term + oxide-barrier Robin term on interface nodes
        # (SurfaceArea - ContactSurfaceArea isolates insulator interfaces;
        # node models are volume-integrated, hence the /NodeVolume)
        nm = (f"{lam} * {u}"
              f" - dg_scale * 2 * {b} / {dpen} * {u}"
              f" * (SurfaceArea - ContactSurfaceArea) / NodeVolume")
        nm_name = f"{lam}NodeTerm"
        CreateNodeModel(device, region, nm_name, nm)
        CreateNodeModelDerivative(device, region, nm_name, nm, lam, carrier)

        # per-edge anisotropy weight from the edge direction cosines
        aniso_terms = [f"{DG_ANISO['x']}*unitx^2", f"{DG_ANISO['y']}*unity^2"]
        if InEdgeModelList(device, region, "unitz"):
            aniso_terms.append(f"{DG_ANISO['z']}*unitz^2")
        aniso = f"({' + '.join(aniso_terms)})"

        em = (f"dg_scale * 2 * {b} * {aniso} * ((({carrier}@n1 + 1)^(0.5)) - "
              f"(({carrier}@n0 + 1)^(0.5))) * EdgeInverseLength")
        em_name = f"{lam}EdgeFlux"
        CreateEdgeModel(device, region, em_name, em)
        CreateEdgeModelDerivatives(device, region, em_name, em, carrier)

        devsim.equation(device=device, region=region,
                        name=f"{lam}Equation", variable_name=lam,
                        node_model=nm_name, edge_model=em_name,
                        variable_update="default")


def create_dg_contact(device: str, contact: str,
                      carriers: tuple = ("Electrons", "Holes")) -> None:
    """Classical boundary: Lambda = 0 on an ohmic contact."""
    for carrier, lam, _, _ in DG_CARRIERS:
        if carrier not in carriers:
            continue
        name = f"{contact}node{lam}"
        CreateContactNodeModel(device, contact, name, lam)
        CreateContactNodeModel(device, contact, f"{name}:{lam}", "1")
        devsim.contact_equation(device=device, contact=contact,
                                name=f"{lam}Equation", node_model=name)
