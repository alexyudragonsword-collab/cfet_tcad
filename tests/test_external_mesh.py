"""Design import: structure=external consumes a user-supplied gmsh mesh.

The donor mesh comes from the parametric nanosheet builder, so the
external path can be cross-validated bit-for-bit against the builder
path on the same geometry.
"""

import pytest
import yaml

import cfet_tcad
from cfet_tcad.geometry import BUILDERS, DeviceParams, MeshParams
from cfet_tcad.geometry.external import read_msh_physical_names
from cfet_tcad.workflow.config import load_config
from cfet_tcad.workflow.runner import run_config

COARSE = dict(nx_sd=6, nx_gate=10, ny_si=5, ny_ox=2)


@pytest.fixture(scope="module")
def donor(tmp_path_factory):
    """A builder-generated mesh plus its layout (the mapping ground truth)."""
    out = tmp_path_factory.mktemp("donor")
    dev = DeviceParams(name="donor", structure="nanosheet_2d",
                       gate_workfunction_ev=4.5)
    layout = BUILDERS["nanosheet_2d"](dev, MeshParams(**COARSE)).build(
        out / "donor.msh")
    return out / "donor.msh", layout


def _external_config(msh_path, layout, **doping):
    return {
        "device": {
            "name": "imported", "structure": "external", "polarity": "n",
            "gate_workfunction_ev": 4.5,
            "external": {
                "mesh_file": str(msh_path), "dimension": layout.dimension,
                "regions": dict(layout.regions),
                "contacts": dict(layout.contacts),
                "interfaces": {k: list(v)
                               for k, v in layout.interfaces.items()},
                **doping,
            },
        },
        "mesh": dict(COARSE),
        "simulation": {"type": "idvg", "vd": [0.7], "vg_start": 0.0,
                       "vg_stop": 0.7, "vg_step": 0.1},
        "output": {"directory": "unused", "vtk": False},
    }


def test_msh_physical_names(donor):
    msh, layout = donor
    names = read_msh_physical_names(msh)
    for group in (list(layout.regions) + list(layout.contacts)
                  + list(layout.interfaces)):
        assert group in names


def test_validation_errors(tmp_path, donor):
    msh, layout = donor
    # unknown physical group -> error names it and lists what exists
    raw = _external_config(msh, layout)
    raw["device"]["external"]["contacts"]["bogus"] = "silicon"
    cfg = _load(tmp_path, raw)
    builder = BUILDERS["external"](cfg.device, cfg.mesh)
    with pytest.raises(ValueError, match="bogus.*silicon"):
        builder.build(tmp_path / "staged.msh")

    # schema errors surface at config validation time
    for breakage, match in (
            ({"mesh_file": None}, "mesh_file"),
            ({"dimension": 5}, "dimension"),
            ({"regions": {"silicon": "Diamond"}}, "Silicon.*Oxide"),
            ({"doping": {"silicon": {"profile": "radial"}}}, "profile"),
    ):
        raw = _external_config(msh, layout)
        raw["device"]["external"].update(breakage)
        with pytest.raises(ValueError, match=match):
            _load(tmp_path, raw)
    # external section is rejected on parametric structures
    with pytest.raises(ValueError, match="external"):
        DeviceParams(structure="nanosheet_2d", external={"a": 1})


def test_msh_version_check(tmp_path):
    bad = tmp_path / "v4.msh"
    bad.write_text("$MeshFormat\n4.1 0 8\n$EndMeshFormat\n")
    with pytest.raises(ValueError, match="msh2"):
        read_msh_physical_names(bad)


def _load(tmp_path, raw):
    p = tmp_path / "cfg.yaml"
    p.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return load_config(p)


def test_relative_mesh_file_resolves_against_config_dir(tmp_path, donor):
    msh, layout = donor
    raw = _external_config("donor.msh", layout)  # relative
    sub = tmp_path / "cfgdir"
    sub.mkdir()
    (sub / "donor.msh").write_bytes(msh.read_bytes())
    cfg = _load(sub, raw)
    assert cfg.device.external["mesh_file"] == str(sub / "donor.msh")


@pytest.mark.slow
def test_external_matches_builder_bit_for_bit(tmp_path, donor):
    """The same mesh solved through the builder path and the external
    path must produce identical currents."""
    msh, layout = donor

    cfet_tcad.reset()
    builder_cfg = _load(tmp_path, {
        "device": {"name": "native", "structure": "nanosheet_2d",
                   "polarity": "n", "gate_workfunction_ev": 4.5},
        "mesh": dict(COARSE),
        "simulation": {"type": "idvg", "vd": [0.7], "vg_start": 0.0,
                       "vg_stop": 0.7, "vg_step": 0.1},
        "output": {"directory": "unused", "vtk": False},
    })
    native = run_config(builder_cfg, tmp_path / "native")

    cfet_tcad.reset()
    ext_cfg = _load(tmp_path, _external_config(
        msh, layout, doping={"silicon": {"profile": "lateral_sd"}}))
    imported = run_config(ext_cfg, tmp_path / "imported")

    for a, b in zip(native["curves"][0]["id"],
                    imported["curves"][0]["id"]):
        assert a == b  # bit-exact: same mesh, same physics


@pytest.mark.slow
def test_external_uniform_doping_runs(tmp_path, donor):
    """The uniform profile registers and solves (a resistor-like slab)."""
    msh, layout = donor
    cfet_tcad.reset()
    cfg = _load(tmp_path, _external_config(
        msh, layout,
        doping={"silicon": {"profile": "uniform",
                            "donors_cm3": 1.0e18, "acceptors_cm3": 0.0}}))
    results = run_config(cfg, tmp_path / "uniform")
    currents = results["curves"][0]["id"]
    assert all(abs(i) > 0 for i in currents)  # conducts at every bias
