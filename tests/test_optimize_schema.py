"""FIELD_BOUNDS is a hand-maintained mirror of the real dataclass
validation (config.py/params.py express bounds as imperative `if`
checks, not declarative metadata) -- these tests catch drift between the
two by round-tripping each bound's min/max through the real
build_config()."""

import pytest

from cfet_tcad.optimize.schema import FIELD_BOUNDS
from cfet_tcad.workflow.config import build_config

BASE_RAW = {
    "device": {"name": "opt_drift", "polarity": "n",
              "structure": "nanosheet_2d"},
}


def _raw_with(path: str, value: float) -> dict:
    raw = {k: dict(v) for k, v in BASE_RAW.items()}
    section, field = path.split(".")
    raw.setdefault(section, {})[field] = value
    return raw


@pytest.mark.parametrize("path", sorted(FIELD_BOUNDS))
def test_bounds_min_and_max_are_accepted(path):
    bounds = FIELD_BOUNDS[path]
    for value in (bounds["min"], bounds["max"]):
        cfg = build_config(_raw_with(path, value))
        section, field = path.split(".")
        got = getattr(getattr(cfg, section), field)
        assert got == pytest.approx(value)


def test_field_bounds_excludes_structural_and_extraction_fields():
    excluded = {
        "device.structure", "device.polarity", "device.external",
        "device.n_fins", "device.n_stacked_sheets", "device.n_sheets",
        "simulation.type", "extract.icrit_a",
        "mesh.nx_sd", "mesh.nx_gate", "mesh.ny_si", "mesh.ny_ox",
        "mesh.nz_w",
    }
    assert not (excluded & set(FIELD_BOUNDS))


def test_field_bounds_min_less_than_max():
    for path, bounds in FIELD_BOUNDS.items():
        assert bounds["min"] < bounds["max"], path
