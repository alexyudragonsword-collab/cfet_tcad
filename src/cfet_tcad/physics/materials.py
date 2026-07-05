"""Material parameter library (cm / s / V / eV unit system, 300 K defaults).

Values follow common TCAD defaults (Sze; Sentaurus parameter files use the
same order of magnitude).  Extend by adding entries to MATERIALS.
"""

from dataclasses import dataclass

Q = 1.602176634e-19        # C
K_B = 1.380649e-23         # J/K
EPS_0 = 8.8541878128e-14   # F/cm


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

SIO2 = InsulatorParams(name="SiO2", eps_r=3.9)
HFO2 = InsulatorParams(name="HfO2", eps_r=22.0)

MATERIALS = {
    "Silicon": SILICON,
    "SiO2": SIO2,
    "HfO2": HFO2,
}


def thermal_voltage(temperature: float) -> float:
    return K_B * temperature / Q
