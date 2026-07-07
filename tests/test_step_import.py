"""STEP import: CAD assembly -> conformal MSH 2.2 -> external pipeline.

The fixture STEP is written with gmsh's own OCC kernel (a silicon slab
with an oxide slab on top, drawn in nm-as-CAD-units), so the tests carry
no binary assets.  Note gmsh's STEP writer emits generic product labels
("Open CASCADE STEP translator ..."), which is exactly the
no-useful-names case the discovery-table workflow is designed for; the
label-regex selector is exercised against those real labels.
"""

from pathlib import Path

import pytest
import yaml

from cfet_tcad.geometry.external import read_msh_physical_names
from cfet_tcad.geometry.step_import import (_volume_table, convert_step,
                                            discover_step,
                                            starter_external_config)

UNIT_CM = 1.0e-7  # fixture drawn in nm


@pytest.fixture(scope="module")
def step_file(tmp_path_factory):
    import gmsh

    out = tmp_path_factory.mktemp("step") / "demo.step"
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("fixture")
        gmsh.model.occ.addBox(0, 0, 0, 30, 6, 10)   # silicon body
        gmsh.model.occ.addBox(0, 6, 0, 30, 2, 10)   # oxide on top
        gmsh.model.occ.synchronize()
        gmsh.write(str(out))
    finally:
        gmsh.finalize()
    return out


def _spec(**overrides):
    spec = {
        "step_file": "demo.step",
        "unit_cm": UNIT_CM,
        "mesh_size": 2.0,
        "regions": {
            # label regex against the real (generic) STEP labels plus a
            # plain volume-tag selector - two of the three selector kinds.
            # Match ".1" (the first solid) not "1.1": gmsh's OCC STEP
            # writer uses a process-global session counter, so the
            # leading number varies once other tests have written STEPs.
            "bulk": {"select": {"label": r"\.1$"}, "material": "Silicon"},
            "gox": {"select": {"volume": 2}, "material": "Oxide"},
        },
        "contacts": {
            "source": {"select": {"bbox": [0, 0, 0, 0, 6, 10]},
                       "region": "bulk"},
            "drain": {"select": {"bbox": [30, 0, 0, 30, 6, 10]},
                      "region": "bulk"},
            "gate": {"select": {"bbox": [0, 8, 0, 30, 8, 10]},
                     "region": "gox"},
        },
        "interfaces": {"si_ox": ["bulk", "gox"]},
    }
    spec.update(overrides)
    return spec


def test_discover_lists_volumes(step_file):
    vols = discover_step(step_file)
    assert [v.tag for v in vols] == [1, 2]
    # OCC bboxes are tolerance-padded: compare loosely
    assert vols[0].bbox[4] == pytest.approx(6, abs=1e-3)
    assert vols[1].bbox[4] == pytest.approx(8, abs=1e-3)
    table = _volume_table(vols)
    assert "tag" in table and "1" in table and "2" in table


def test_convert_writes_msh22_with_all_groups(step_file, tmp_path):
    msh = tmp_path / "demo.msh"
    summary = convert_step(_spec(), step_file.parent, msh)
    assert summary["regions"] == {"bulk": 1, "gox": 1}
    assert summary["nodes"] > 0
    # read_msh_physical_names doubles as the MSH-2.2 version gate
    names = read_msh_physical_names(msh)
    for group in ("bulk", "gox", "source", "drain", "gate", "si_ox"):
        assert group in names

    # unit scaling: node coordinates are CAD bbox x unit_cm
    xs, in_nodes = [], False
    for line in msh.read_text().splitlines():
        if line.startswith("$Nodes"):
            in_nodes = True
        elif line.startswith("$EndNodes"):
            break
        elif in_nodes:
            parts = line.split()
            if len(parts) == 4:
                xs.append(float(parts[1]))
    assert min(xs) == pytest.approx(0, abs=1e-9)
    assert max(xs) == pytest.approx(30 * UNIT_CM, rel=1e-6)


def test_selector_and_mapping_errors(step_file, tmp_path):
    msh = tmp_path / "x.msh"
    # unclaimed volume: the error carries the reference table
    spec = _spec()
    del spec["regions"]["gox"]
    del spec["contacts"]["gate"]
    del spec["interfaces"]["si_ox"]
    with pytest.raises(ValueError, match=r"(?s)not claimed.*tag"):
        convert_step(spec, step_file.parent, msh)

    # bbox selector for regions (third selector kind) + double claim
    spec = _spec()
    spec["regions"]["gox2"] = {"select": {"bbox": [0, 6, 0, 30, 8, 10]},
                               "material": "Oxide"}
    with pytest.raises(ValueError, match="claimed by both"):
        convert_step(spec, step_file.parent, msh)

    # contact bbox that touches nothing of its owner region
    spec = _spec()
    spec["contacts"]["gate"]["select"]["bbox"] = [500, 500, 500,
                                                  501, 501, 501]
    with pytest.raises(ValueError, match="gate.*matched no face"):
        convert_step(spec, step_file.parent, msh)

    # unit_cm is mandatory
    spec = _spec()
    del spec["unit_cm"]
    with pytest.raises(ValueError, match="unit_cm"):
        convert_step(spec, step_file.parent, msh)


def test_fig4_demo_generator_converts_cleanly(tmp_path):
    """The shipped paper-Fig.4 FBC example: generator -> spec ->
    conversion, with the gate contact NOT swallowing the Si-SiO2
    interface faces (contacts are exterior-only)."""
    import sys
    sys.path.insert(0, "examples")
    try:
        from make_paper_fig4_step import build_step, import_spec
    finally:
        sys.path.pop(0)

    step = tmp_path / "demo.step"
    build_step(step)
    spec = import_spec(step.name)
    msh = tmp_path / "demo.msh"
    summary = convert_step(spec, tmp_path, msh)
    # two fins / two shells per device, all claimed
    assert summary["regions"] == {"silicon_n": 2, "oxide_n": 2,
                                  "silicon_p": 2, "oxide_p": 2}
    names = read_msh_physical_names(msh)
    for group in ("silicon_n", "oxide_n", "silicon_p", "oxide_p",
                  "source_n", "drain_n", "gate_n", "source_p", "drain_p",
                  "gate_p", "si_ox_n", "si_ox_p"):
        assert group in names

    # exterior filter: no mesh face may be tagged both gate and
    # interface (count element lines per 2D physical group in the MSH)
    import gmsh
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.open(str(msh))
        groups = {gmsh.model.getPhysicalName(d, t): (d, t)
                  for d, t in gmsh.model.getPhysicalGroups(2)}
        def faces(name):
            d, t = groups[name]
            out = set()
            for e in gmsh.model.getEntitiesForPhysicalGroup(d, t):
                out.add(e)
            return out
        assert faces("gate_n") and faces("si_ox_n")
        assert not faces("gate_n") & faces("si_ox_n")
        assert not faces("gate_p") & faces("si_ox_p")
    finally:
        gmsh.finalize()

    # the shipped copies in configs/ stay in sync with the generator
    shipped = Path("configs/paper_fbc_cfet_demo_import.yaml")
    if shipped.exists():
        import yaml as _yaml
        on_disk = _yaml.safe_load(shipped.read_text(encoding="utf-8"))
        assert on_disk == import_spec("paper_fbc_cfet_demo.step")


def test_sbc_demo_generator_converts_cleanly(tmp_path):
    """The shipped paper SBC example: two vertically stacked nanosheets
    per device.  Same guarantees as the FBC demo - all groups present,
    gate contacts exterior-only (no interface faces swallowed)."""
    import sys
    sys.path.insert(0, "examples")
    try:
        from make_paper_sbc_step import build_step, import_spec
    finally:
        sys.path.pop(0)

    step = tmp_path / "sbc.step"
    build_step(step)
    spec = import_spec(step.name)
    msh = tmp_path / "sbc.msh"
    summary = convert_step(spec, tmp_path, msh)
    # two sheets / two shells per device, all claimed
    assert summary["regions"] == {"silicon_n": 2, "oxide_n": 2,
                                  "silicon_p": 2, "oxide_p": 2}
    names = read_msh_physical_names(msh)
    for group in ("silicon_n", "oxide_n", "silicon_p", "oxide_p",
                  "source_n", "drain_n", "gate_n", "source_p", "drain_p",
                  "gate_p", "si_ox_n", "si_ox_p"):
        assert group in names

    import gmsh
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.open(str(msh))
        groups = {gmsh.model.getPhysicalName(d, t): (d, t)
                  for d, t in gmsh.model.getPhysicalGroups(2)}

        def faces(name):
            d, t = groups[name]
            return set(gmsh.model.getEntitiesForPhysicalGroup(d, t))
        assert faces("gate_n") and faces("si_ox_n")
        assert not faces("gate_n") & faces("si_ox_n")
        assert not faces("gate_p") & faces("si_ox_p")
    finally:
        gmsh.finalize()

    shipped = Path("configs/paper_sbc_cfet_demo_import.yaml")
    if shipped.exists():
        import yaml as _yaml
        on_disk = _yaml.safe_load(shipped.read_text(encoding="utf-8"))
        assert on_disk == import_spec("paper_sbc_cfet_demo.step")


def test_starter_config_picks_sim_type_from_contacts(tmp_path):
    # single device -> plain idvg (contacts source/drain/gate)
    single = {"regions": {"bulk": {"select": {}, "material": "Silicon"},
                          "gox": {"select": {}, "material": "Oxide"}},
              "contacts": {"source": {"region": "bulk"},
                           "drain": {"region": "bulk"},
                           "gate": {"region": "gox"}}}
    cfg = starter_external_config(single, tmp_path / "d.msh")
    assert cfg["simulation"]["type"] == "idvg"

    # CFET stack (_n/_p sub-devices) -> cfet_idvg, so it never crashes on
    # a missing "drain" contact; polarity/workfunctions inferred by suffix
    cfet = {"regions": {"silicon_n": {"select": {}, "material": "Silicon"},
                        "oxide_n": {"select": {}, "material": "Oxide"},
                        "silicon_p": {"select": {}, "material": "Silicon"},
                        "oxide_p": {"select": {}, "material": "Oxide"}},
            "contacts": {"source_n": {"region": "silicon_n"},
                         "drain_n": {"region": "silicon_n"},
                         "gate_n": {"region": "oxide_n"},
                         "source_p": {"region": "silicon_p"},
                         "drain_p": {"region": "silicon_p"},
                         "gate_p": {"region": "oxide_p"}}}
    cfg = starter_external_config(cfet, tmp_path / "s.msh")
    assert cfg["simulation"]["type"] == "cfet_idvg"
    ext = cfg["device"]["external"]
    assert ext["silicon_polarity"] == {"silicon_n": "n", "silicon_p": "p"}
    assert ext["gate_workfunctions"] == {"gate_n": 4.50, "gate_p": 4.72}


@pytest.mark.slow
def test_converted_mesh_solves_through_external(step_file, tmp_path):
    from cfet_tcad.workflow.config import load_config
    from cfet_tcad.workflow.runner import run_config

    msh = tmp_path / "demo.msh"
    convert_step(_spec(), step_file.parent, msh)
    raw = starter_external_config(_spec(), msh)
    raw["simulation"] = {"type": "idvg", "vd": [0.05], "vg_start": 0.0,
                         "vg_stop": 0.2, "vg_step": 0.1}
    raw["output"] = {"directory": str(tmp_path / "run"), "vtk": False}
    cfg_path = tmp_path / "demo.yaml"
    cfg_path.write_text(yaml.safe_dump(raw, sort_keys=False),
                        encoding="utf-8")
    results = run_config(load_config(cfg_path), tmp_path / "run")
    assert "Vd = +0.05 V" in results["fom"]
