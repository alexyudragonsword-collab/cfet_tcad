"""Material parameter library (cm / s / V / eV unit system, 300 K defaults).

Values follow common TCAD defaults (Sze; Sentaurus parameter files use the
same order of magnitude).  Extend by adding entries to MATERIALS.
"""

from dataclasses import dataclass

Q = 1.602176634e-19        # C
K_B = 1.380649e-23         # J/K
EPS_0 = 8.8541878128e-14   # F/cm
HBAR = 1.054571817e-34     # J s
M0 = 9.1093837015e-31      # kg


@dataclass(frozen=True)
class SemiconductorParams:
    name: str
    eps_r: float
    n_i: float               # intrinsic carrier density [cm^-3]
    affinity_ev: float       # electron affinity chi [eV]
    eg_ev: float             # band gap [eV]
    # Caughey-Thomas doping-dependent low-field mobility [cm^2/Vs]
    mu_max_n: float
    mu_min_n: float
    nref_n: float
    alpha_n: float
    mu_max_p: float
    mu_min_p: float
    nref_p: float
    alpha_p: float
    # velocity saturation
    vsat_n: float             # [cm/s]
    vsat_p: float
    beta_n: float
    beta_p: float
    # density-gradient effective masses (fraction of m0); calibration knobs
    # for the quantum-confinement strength, scaled further by dg_gamma_*
    m_dg_n: float = 0.3
    m_dg_p: float = 0.4
    # Lombardi CVT surface scattering: acoustic phonon B [cm/s] and
    # surface roughness delta [cm^2/Vs] (classic Si values)
    b_ac_n: float = 4.75e7
    b_ac_p: float = 9.925e6
    delta_sr_n: float = 5.82e14
    delta_sr_p: float = 2.055e14

    @property
    def midgap_workfunction_ev(self) -> float:
        """Vacuum -> intrinsic level distance; reference for metal gate WF."""
        return self.affinity_ev + 0.5 * self.eg_ev


@dataclass(frozen=True)
class InsulatorParams:
    name: str
    eps_r: float


SILICON = SemiconductorParams(
    name="Silicon",
    eps_r=11.7,
    n_i=1.0e10,
    affinity_ev=4.05,
    eg_ev=1.12,
    mu_max_n=1414.0, mu_min_n=68.5, nref_n=9.20e16, alpha_n=0.711,
    mu_max_p=470.5, mu_min_p=44.9, nref_p=2.23e17, alpha_p=0.719,
    vsat_n=1.07e7, vsat_p=8.37e6, beta_n=2.0, beta_p=1.0,
)

import math
import re


def sige(x: float) -> SemiconductorParams:
    """Compressively strained Si(1-x)Ge(x) on Si, linear interpolation
    anchored so sige(0) matches Silicon and sige(0.30) the classic SiGe30
    values.  The bandgap narrows ~0.14 eV per 30% Ge (mostly a valence
    band offset) and the strain-enhanced hole mobility is the reason
    industry uses it: it rebalances pFET drive against the nFET.
    Saturation velocity and the CVT/DG parameters stay at their Si values
    (calibration knobs)."""
    if not 0.0 <= x <= 0.5:
        raise ValueError(
            f"Ge fraction {x} outside the strained-on-Si range [0, 0.5]")
    eg = SILICON.eg_ev - 0.467 * x
    vt300 = K_B * 300.0 / Q
    n_i = SILICON.n_i * math.exp((SILICON.eg_ev - eg) / (2.0 * vt300))
    return SemiconductorParams(
        name=f"SiGe{round(x * 100)}",
        eps_r=SILICON.eps_r + 1.67 * x,
        n_i=n_i,
        affinity_ev=SILICON.affinity_ev,
        eg_ev=eg,
        mu_max_n=SILICON.mu_max_n - 1380.0 * x,
        mu_min_n=SILICON.mu_min_n - 28.3 * x,
        nref_n=SILICON.nref_n, alpha_n=SILICON.alpha_n,
        mu_max_p=SILICON.mu_max_p + 1432.0 * x,
        mu_min_p=SILICON.mu_min_p + 50.3 * x,
        nref_p=SILICON.nref_p, alpha_p=SILICON.alpha_p,
        vsat_n=1.0e7, vsat_p=8.4e6,
        beta_n=SILICON.beta_n, beta_p=SILICON.beta_p,
    )


SIGE30 = sige(0.30)

SIO2 = InsulatorParams(name="SiO2", eps_r=3.9)
HFO2 = InsulatorParams(name="HfO2", eps_r=22.0)

MATERIALS = {
    "Silicon": SILICON,
    "SiGe30": SIGE30,
    "SiO2": SIO2,
    "HfO2": HFO2,
}

_SIGE_KEY = re.compile(r"^SiGe(\d{1,2})$")


def get_material(key: str):
    """Resolve a material key: exact MATERIALS entry, or a dynamic
    'SiGeNN' composition (NN = Ge percent, e.g. SiGe15 -> x=0.15)."""
    if key in MATERIALS:
        return MATERIALS[key]
    m = _SIGE_KEY.match(key)
    if m:
        return sige(int(m.group(1)) / 100.0)
    raise ValueError(
        f"unknown material {key!r}; available: {sorted(MATERIALS)} "
        f"or dynamic 'SiGeNN' (NN = Ge percent, 0-50)")


def thermal_voltage(temperature: float) -> float:
    return K_B * temperature / Q
