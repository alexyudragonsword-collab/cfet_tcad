"""Mobility models.

Three levels, selected via config ``physics.mobility.model``:

- ``const``       : constant mu_n / mu_p parameters
- ``doping``      : Caughey-Thomas doping-dependent low-field mobility
- ``doping_vsat`` : additionally Caughey-Thomas velocity saturation driven
                    by the field along each edge (default)

Each builder returns the mobility *expression strings* (mu_n, mu_p) to be
inlined into the Scharfetter-Gummel edge currents.  Inlining lets DEVSIM's
symbolic diff() produce exact Newton derivatives, including the dependence
of the saturated mobility on Potential.

A hook for vertical-field (transverse) degradation — Lombardi-style, needed
for accurate surface mobility — is reserved for Phase 2: it requires
element-based field reconstruction and element edge currents in DEVSIM.
"""

import devsim
from devsim.python_packages.model_create import CreateNodeModel

from .materials import SemiconductorParams

#: "lombardi_vsat" adds CVT vertical-field degradation via element-based
#: currents (2D only); assembled in physics.lombardi after the classical
#: system converges
MOBILITY_MODELS = ("const", "doping", "doping_vsat", "lombardi_vsat")


def _create_lowfield_edge_models(device: str, region: str,
                                 mat: SemiconductorParams,
                                 scale_n: float = 1.0,
                                 scale_p: float = 1.0) -> None:
    """Doping-dependent low-field mobility, averaged onto edges.

    Depends only on the (fixed) doping, so no solution derivatives are
    needed; symbolic diff of the edge models w.r.t. any solution variable
    is zero and they can be referenced by name inside current expressions.

    ``scale_n`` / ``scale_p`` are calibration multipliers (surface
    orientation, strain, BTE matching - the knobs a drift-diffusion
    flow tunes against a higher-order reference).  1.0 leaves the
    expressions character-identical to the uncalibrated form.
    """
    mu_n = (f"{mat.mu_min_n} + ({mat.mu_max_n} - {mat.mu_min_n})"
            f"/(1 + (TotalDoping/{mat.nref_n})^{mat.alpha_n})")
    mu_p = (f"{mat.mu_min_p} + ({mat.mu_max_p} - {mat.mu_min_p})"
            f"/(1 + (TotalDoping/{mat.nref_p})^{mat.alpha_p})")
    if scale_n != 1.0:
        mu_n = f"{scale_n} * ({mu_n})"
    if scale_p != 1.0:
        mu_p = f"{scale_p} * ({mu_p})"
    CreateNodeModel(device, region, "mu_n_lf_node", mu_n)
    CreateNodeModel(device, region, "mu_p_lf_node", mu_p)
    for nmodel, emodel in (("mu_n_lf_node", "mu_n_lf"),
                           ("mu_p_lf_node", "mu_p_lf")):
        devsim.edge_average_model(device=device, region=region,
                                  node_model=nmodel, edge_model=emodel,
                                  average_type="arithmetic")


# smooth |E_parallel| along the edge; +1e-4 (V/cm)^2 keeps it differentiable
_EPAR = "((((Potential@n0 - Potential@n1)*EdgeInverseLength)^2 + 1e-4)^(0.5))"


def create_mobility(device: str, region: str, mat: SemiconductorParams,
                    model: str = "doping_vsat",
                    scale_n: float = 1.0,
                    scale_p: float = 1.0) -> tuple[str, str]:
    """Set up mobility models on ``region``; return (mu_n, mu_p) expressions."""
    if model not in MOBILITY_MODELS:
        raise ValueError(
            f"unknown mobility model {model!r}, expected one of {MOBILITY_MODELS}")
    if model == "lombardi_vsat":
        raise ValueError("lombardi_vsat is assembled by physics.lombardi "
                         "after the classical solve, not by create_mobility")

    if model == "const":
        return "mu_n", "mu_p"

    _create_lowfield_edge_models(device, region, mat,
                                 scale_n=scale_n, scale_p=scale_p)
    if model == "doping":
        return "mu_n_lf", "mu_p_lf"

    devsim.set_parameter(device=device, region=region, name="vsat_n",
                         value=mat.vsat_n)
    devsim.set_parameter(device=device, region=region, name="vsat_p",
                         value=mat.vsat_p)
    mu_n = (f"(mu_n_lf * (1 + (mu_n_lf*{_EPAR}/vsat_n)^{mat.beta_n})"
            f"^(-1/{mat.beta_n}))")
    mu_p = (f"(mu_p_lf * (1 + (mu_p_lf*{_EPAR}/vsat_p)^{mat.beta_p})"
            f"^(-1/{mat.beta_p}))")
    return mu_n, mu_p
