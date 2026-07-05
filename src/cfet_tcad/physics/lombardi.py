"""Lombardi (CVT) vertical-field mobility degradation, element-based.

Surface acoustic-phonon and surface-roughness scattering reduce the
inversion-layer mobility with the field transverse to transport:

    1/mu = 1/mu_lf + cvt_scale*(E_perp/B + E_perp^2/delta)

combined by Matthiessen's rule with the doping-dependent low-field
mobility, then Caughey-Thomas velocity saturation on top.  E_perp needs a
vector field, which lives beyond scalar edge models: the electric field is
reconstructed per element edge (``element_from_edge_model``) and the
Scharfetter-Gummel currents are re-assembled as *element* models wired
into the continuity and contact equations.

Accessor discipline (verified empirically): in element expressions,
``@n0``/``@en0`` evaluate identically but differentiate as *independent*
symbols — everything with solution dependence must be written with the
``@en*`` accessors, while purely geometric edge models
(EdgeInverseLength, unitx/unity) and the doping-only ``mu_*_lf`` are safe
to reference by name.  Element-context diff() resolves named element
models through their ``model:var@en*`` derivative models.

2D regions only (the derivative helper covers @en0..@en2 triangles).
``cvt_scale`` (0 -> no degradation, 1 -> full) is the homotopy knob.
"""

import devsim
from devsim.python_packages.model_create import (
    CreateElementModel2d,
    CreateElementModelDerivative2d,
)

from .materials import SemiconductorParams

ECE_NAME = "ElectronContinuityEquation"
HCE_NAME = "HoleContinuityEquation"

# E_perp^2 floor: 1e2 (V/cm)^2 -> 10 V/cm, far below the ~1e5 V/cm
# degradation onset yet safely above reconstruction rounding noise
_EPERP = ("(((ElectricField_x^2 + ElectricField_y^2)"
          " - (ElectricField_x*unitx + ElectricField_y*unity)^2"
          " + 1e2)^(0.5))")
# transport-direction field for velocity saturation (edge-aligned)
_EPAR = "((((Potential@en0 - Potential@en1)*EdgeInverseLength)^2 + 1e-4)^(0.5))"

_VDIFF = "((Potential@en0 - Potential@en1)/V_t)"


def apply_lombardi_currents(device: str, region: str,
                            mat: SemiconductorParams) -> None:
    """Replace the edge SG currents of ``region`` with element currents
    carrying the CVT mobility.  Call after the classical drift-diffusion
    system is assembled and solved (mobility model 'doping', so the
    mu_*_lf edge models exist)."""
    p = devsim.set_parameter
    p(device=device, region=region, name="b_ac_n", value=mat.b_ac_n)
    p(device=device, region=region, name="b_ac_p", value=mat.b_ac_p)
    p(device=device, region=region, name="delta_sr_n", value=mat.delta_sr_n)
    p(device=device, region=region, name="delta_sr_p", value=mat.delta_sr_p)
    p(device=device, region=region, name="vsat_n", value=mat.vsat_n)
    p(device=device, region=region, name="vsat_p", value=mat.vsat_p)
    # classical limit until the homotopy ramps it up
    devsim.set_parameter(device=device, name="cvt_scale", value=0.0)

    devsim.element_from_edge_model(edge_model="ElectricField",
                                   device=device, region=region)
    devsim.element_from_edge_model(edge_model="ElectricField",
                                   derivative="Potential",
                                   device=device, region=region)

    for s, beta in (("n", mat.beta_n), ("p", mat.beta_p)):
        mu0 = (f"(1/(1/mu_{s}_lf"
               f" + cvt_scale*{_EPERP}/b_ac_{s}"
               f" + cvt_scale*({_EPERP}^2)/delta_sr_{s}))")
        mu = f"({mu0}/(1 + ({mu0}*{_EPAR}/vsat_{s})^{beta})^(1/{beta}))"
        name = f"mu_{s}_cvt"
        CreateElementModel2d(device, region, name, mu)
        CreateElementModelDerivative2d(device, region, name, mu, "Potential")

    bern = f"B({_VDIFF})"
    jn = (f"ElectronCharge*mu_n_cvt*EdgeInverseLength*V_t*"
          f"kahan3(Electrons@en1*{bern}, Electrons@en1*{_VDIFF},"
          f" -Electrons@en0*{bern})")
    CreateElementModel2d(device, region, "ElectronCurrentE", jn)
    for var in ("Potential", "Electrons"):
        CreateElementModelDerivative2d(device, region, "ElectronCurrentE",
                                       jn, var)

    jp = (f"-ElectronCharge*mu_p_cvt*EdgeInverseLength*V_t*"
          f"kahan3(Holes@en1*{bern}, -Holes@en0*{bern},"
          f" -Holes@en0*{_VDIFF})")
    CreateElementModel2d(device, region, "HoleCurrentE", jp)
    for var in ("Potential", "Holes"):
        CreateElementModelDerivative2d(device, region, "HoleCurrentE",
                                       jp, var)

    devsim.equation(device=device, region=region, name=ECE_NAME,
                    variable_name="Electrons", time_node_model="NCharge",
                    edge_model="", element_model="ElectronCurrentE",
                    node_model="ElectronGeneration",
                    variable_update="positive")
    devsim.equation(device=device, region=region, name=HCE_NAME,
                    variable_name="Holes", time_node_model="PCharge",
                    edge_model="", element_model="HoleCurrentE",
                    node_model="HoleGeneration",
                    variable_update="positive")


def rewire_lombardi_contact(device: str, contact: str,
                            circuit_node: str | None = None) -> None:
    """Point the contact continuity equations at the element currents."""
    extra = {} if circuit_node is None else {"circuit_node": circuit_node}
    devsim.contact_equation(device=device, contact=contact, name=ECE_NAME,
                            node_model=f"{contact}nodeelectrons",
                            element_current_model="ElectronCurrentE",
                            **extra)
    devsim.contact_equation(device=device, contact=contact, name=HCE_NAME,
                            node_model=f"{contact}nodeholes",
                            element_current_model="HoleCurrentE",
                            **extra)
