"""YAML simulation configuration parsing and validation."""

import dataclasses
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from ..geometry.params import DeviceParams, MeshParams
from ..physics.mobility import MOBILITY_MODELS


QUANTUM_MODELS = ("none", "density_gradient")


@dataclass
class PhysicsConfig:
    temperature: float = 300.0
    taun: float = 1e-7
    taup: float = 1e-7
    mobility_model: str = "doping_vsat"
    oxide_material: str = "SiO2"
    quantum_model: str = "none"
    dg_gamma_n: float = 1.0   # scale factors on the DG coefficients
    dg_gamma_p: float = 1.0

    def __post_init__(self):
        if self.mobility_model not in MOBILITY_MODELS:
            raise ValueError(
                f"mobility_model must be one of {MOBILITY_MODELS}")
        if self.quantum_model not in QUANTUM_MODELS:
            raise ValueError(
                f"quantum_model must be one of {QUANTUM_MODELS}")


@dataclass
class SimulationConfig:
    type: str = "idvg"     # "idvg" | "idvd" | "cfet_idvg" | "cfet_vtc"
    vd: list = field(default_factory=lambda: [0.05, 0.7])  # idvg: Vd values
    vg: list = field(default_factory=lambda: [0.7])        # idvd: Vg values
    vg_start: float = 0.0
    vg_stop: float = 0.7
    vg_step: float = 0.025
    vd_start: float = 0.0
    vd_stop: float = 0.7
    vd_step: float = 0.025
    vdd: float = 0.7       # cfet_idvg: rail voltage (pFET source, nFET drain)
    min_step: float = 1e-4

    def __post_init__(self):
        if self.type not in ("idvg", "idvd", "cfet_idvg", "cfet_vtc"):
            raise ValueError(
                "simulation.type must be 'idvg', 'idvd', 'cfet_idvg' "
                "or 'cfet_vtc'")


@dataclass
class OutputConfig:
    directory: str = "results"
    vtk: bool = True
    vtk_stride: int = 5  # write every Nth bias point (plus first/last)


@dataclass
class ExtractConfig:
    icrit_a: float = 1e-8  # constant-current Vt criterion, width-scaled


@dataclass
class RunConfig:
    device: DeviceParams
    mesh: MeshParams
    physics: PhysicsConfig
    simulation: SimulationConfig
    output: OutputConfig
    extract: ExtractConfig


def _coerce(cls, data: dict) -> dict:
    """Cast YAML scalars to the dataclass field types.  PyYAML follows the
    YAML 1.1 float syntax, so '1.0e20' (no sign) arrives as a string."""
    types = {f.name: f.type for f in dataclasses.fields(cls)}
    out = {}
    for key, value in data.items():
        t = types.get(key)
        if t in ("float", float) and isinstance(value, (str, int)):
            value = float(value)
        elif t in ("int", int) and isinstance(value, str):
            value = int(value)
        elif isinstance(value, list):
            value = [float(v) if isinstance(v, str) else v for v in value]
        out[key] = value
    return out


def _build(cls, data: dict, section: str):
    try:
        return cls(**_coerce(cls, data or {}))
    except TypeError as exc:
        raise ValueError(f"invalid key in '{section}' section: {exc}") from exc


def build_config(raw: dict) -> RunConfig:
    return RunConfig(
        device=_build(DeviceParams, raw.get("device"), "device"),
        mesh=_build(MeshParams, raw.get("mesh"), "mesh"),
        physics=_build(PhysicsConfig, raw.get("physics"), "physics"),
        simulation=_build(SimulationConfig, raw.get("simulation"), "simulation"),
        output=_build(OutputConfig, raw.get("output"), "output"),
        extract=_build(ExtractConfig, raw.get("extract"), "extract"),
    )


def apply_overrides(raw: dict, overrides: dict) -> dict:
    """Apply dotted-path overrides (e.g. {"device.l_gate_nm": 12}) to a raw
    config dict.  Returns a deep-ish copy; the input is not modified."""
    import copy

    out = copy.deepcopy(raw)
    for path, value in overrides.items():
        keys = path.split(".")
        node = out
        for key in keys[:-1]:
            node = node.setdefault(key, {})
            if not isinstance(node, dict):
                raise ValueError(f"cannot override through non-dict at "
                                 f"{key!r} in {path!r}")
        node[keys[-1]] = value
    return out


def load_config(path: Path, overrides: dict | None = None) -> RunConfig:
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    if overrides:
        raw = apply_overrides(raw, overrides)
    return build_config(raw)
