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
