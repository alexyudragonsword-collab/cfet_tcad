"""YAML config parsing, including YAML-1.1 float quirks."""

import pytest

from cfet_tcad.workflow.config import load_config


def test_load_example_config():
    cfg = load_config("configs/nsheet_nfet_2d.yaml")
    assert cfg.device.polarity == "n"
    assert cfg.device.sd_doping_cm3 == pytest.approx(1e20)
    assert cfg.simulation.type == "idvg"
    assert cfg.simulation.vd == [0.05, 0.7]


def test_yaml_11_exponent_strings_coerced(tmp_path):
    # '1.0e20' (no sign) is a *string* under YAML 1.1; must still parse
    p = tmp_path / "c.yaml"
    p.write_text(
        "device:\n  sd_doping_cm3: 1.0e20\n  channel_doping_cm3: 5e15\n")
    cfg = load_config(p)
    assert cfg.device.sd_doping_cm3 == pytest.approx(1e20)
    assert cfg.device.channel_doping_cm3 == pytest.approx(5e15)


def test_unknown_key_rejected(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("device:\n  no_such_knob: 1\n")
    with pytest.raises(ValueError, match="device"):
        load_config(p)


def test_bad_mobility_model_rejected(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("physics:\n  mobility_model: quantum_magic\n")
    with pytest.raises(ValueError, match="mobility_model"):
        load_config(p)


def test_simulation_types_accepted_and_rejected(tmp_path):
    structure = {"idvg": "nanosheet_2d", "idvd": "nanosheet_2d",
                 "cfet_idvg": "cfet_2d", "cfet_idvd": "cfet_2d",
                 "cfet_vtc": "cfet_2d"}
    for t, s in structure.items():
        p = tmp_path / "c.yaml"
        p.write_text(f"device:\n  structure: {s}\n"
                     f"simulation:\n  type: {t}\n")
        assert load_config(p).simulation.type == t
    bad = tmp_path / "bad.yaml"
    bad.write_text("simulation:\n  type: cfet_magic\n")
    with pytest.raises(ValueError, match="simulation.type"):
        load_config(bad)


def test_zero_steps_and_bad_scalars_rejected(tmp_path):
    for body in ("simulation:\n  vg_step: 0\n",
                 "simulation:\n  vd_step: 0.0\n",
                 "simulation:\n  min_step: 0\n",
                 "output:\n  vtk_stride: 0\n",
                 "extract:\n  icrit_a: 0\n"):
        p = tmp_path / "c.yaml"
        p.write_text(body)
        with pytest.raises(ValueError):
            load_config(p)


def test_empty_bias_lists_rejected(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("simulation:\n  type: idvg\n  vd: []\n")
    with pytest.raises(ValueError, match="vd"):
        load_config(p)
    p.write_text("simulation:\n  type: idvd\n  vg: []\n")
    with pytest.raises(ValueError, match="vg"):
        load_config(p)


def test_bad_value_error_names_its_section(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("physics:\n  mobility_scale_n: -1\n")
    with pytest.raises(ValueError, match="physics"):
        load_config(p)


def test_sim_structure_cross_validation(tmp_path):
    from cfet_tcad.workflow.config import check_sim_structure

    def cfg_for(structure, sim):
        p = tmp_path / "c.yaml"
        p.write_text(f"device:\n  structure: {structure}\n"
                     f"simulation:\n  type: {sim}\n")
        return load_config(p)

    # loading stays permissive (structure preview pairs a CFET structure
    # with the default sim type); the runner-side check rejects
    with pytest.raises(ValueError, match="CFET stack"):
        check_sim_structure(cfg_for("nanosheet_2d", "cfet_idvg"))
    with pytest.raises(ValueError, match="cfet_"):
        check_sim_structure(cfg_for("cfet_2d", "idvd"))
    check_sim_structure(cfg_for("cfet_2d", "cfet_vtc"))    # matched: fine
    check_sim_structure(cfg_for("gaa_3d", "idvg"))         # matched: fine


def test_n_sheets_conflicts_with_geometric_replication(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("device:\n  structure: cfet_3d\n  n_fins: 2\n"
                 "  n_sheets: 2\nsimulation:\n  type: cfet_idvg\n")
    with pytest.raises(ValueError, match="n_sheets"):
        load_config(p)
