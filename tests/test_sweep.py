"""Sweep engine: spec parsing, overrides, flattening, and a 2-point
end-to-end smoke on a deliberately tiny problem."""

import csv

import pytest

from cfet_tcad.workflow.config import apply_overrides, load_config
from cfet_tcad.workflow.sweep import (
    flatten_fom,
    load_points_csv,
    parse_param_spec,
    points_to_zip_specs,
    run_sweep,
)


def test_parse_param_spec():
    path, values = parse_param_spec("device.l_gate_nm=12,15.5,foo")
    assert path == "device.l_gate_nm"
    assert values == [12, 15.5, "foo"]
    with pytest.raises(ValueError):
        parse_param_spec("no_equals_sign")


def test_apply_overrides_is_nondestructive():
    raw = {"device": {"l_gate_nm": 15.0}}
    out = apply_overrides(raw, {"device.l_gate_nm": 12.0,
                                "physics.mobility_model": "const"})
    assert out["device"]["l_gate_nm"] == 12.0
    assert out["physics"]["mobility_model"] == "const"
    assert raw["device"]["l_gate_nm"] == 15.0  # input untouched


def test_overrides_reach_validated_config(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("device:\n  l_gate_nm: 15.0\n")
    cfg = load_config(p, overrides={"device.l_gate_nm": 21.0})
    assert cfg.device.l_gate_nm == 21.0
    with pytest.raises(ValueError):  # validation still applies
        load_config(p, overrides={"device.polarity": "x"})


def test_zip_params_pairing(tmp_path):
    """--zip pairs the value lists instead of taking the product; unequal
    lengths are rejected before any simulation starts."""
    from cfet_tcad.workflow.sweep import run_sweep

    with pytest.raises(ValueError, match="equally long"):
        run_sweep(tmp_path / "unused.yaml",
                  {"a.b": [1, 2, 3], "c.d": [4, 5]},
                  tmp_path / "out", zip_params=True)


def test_load_points_csv(tmp_path, capsys):
    p = tmp_path / "doe.csv"
    p.write_text("device.l_gate_nm,physics.mobility_model,status\n"
                 "12,doping_vsat,ok\n"
                 "15.5,lombardi_vsat,ok\n", encoding="utf-8")
    points = load_points_csv(p)
    # non-config column (status) is dropped with a notice - an edited
    # sweep_summary.csv round-trips
    assert "status" in capsys.readouterr().out
    assert points == [
        {"device.l_gate_nm": 12, "physics.mobility_model": "doping_vsat"},
        {"device.l_gate_nm": 15.5,
         "physics.mobility_model": "lombardi_vsat"},
    ]
    with pytest.raises(ValueError, match="no parameter columns"):
        bad = tmp_path / "bad.csv"
        bad.write_text("foo,bar\n1,2\n", encoding="utf-8")
        load_points_csv(bad)


def test_points_to_zip_specs():
    lines = points_to_zip_specs([
        {"device.l_gate_nm": 12, "device.polarity": "n"},
        {"device.l_gate_nm": 15},  # missing cell repeats previous value
    ])
    assert lines == ["device.l_gate_nm=12,15", "device.polarity=n,n"]


def test_run_sweep_requires_one_point_source(tmp_path):
    with pytest.raises(ValueError, match="exactly one"):
        run_sweep(tmp_path / "c.yaml", None, tmp_path / "out")
    with pytest.raises(ValueError, match="exactly one"):
        run_sweep(tmp_path / "c.yaml", {"a.b": [1]}, tmp_path / "out",
                  points=[{"a.b": 1}])


def test_flatten_fom():
    fom = {"Vd = +0.70 V": {"ss_mv_per_dec": 74.0}, "dibl_mv_per_v": 90.0}
    flat = flatten_fom(fom)
    assert flat["Vd = +0.70 V.ss_mv_per_dec"] == 74.0
    assert flat["dibl_mv_per_v"] == 90.0


@pytest.mark.slow
def test_sweep_two_points_end_to_end(tmp_path):
    cfg = tmp_path / "tiny.yaml"
    cfg.write_text("""
device: {name: sweep_t, polarity: n, gate_workfunction_ev: 4.5}
mesh: {nx_sd: 6, nx_gate: 10, ny_si: 5, ny_ox: 2}
simulation: {type: idvg, vd: [0.7], vg_start: 0.0, vg_stop: 0.7, vg_step: 0.1}
output: {directory: unused, vtk: false}
""")
    rows = run_sweep(cfg, {"device.l_gate_nm": [15.0, 21.0]},
                     tmp_path / "sweep", jobs=2)
    assert [r["status"] for r in rows] == ["ok", "ok"]
    # longer channel -> better (smaller) subthreshold swing
    ss = {r["device.l_gate_nm"]: r["Vd = +0.70 V.ss_mv_per_dec"]
          for r in rows}
    assert ss[21.0] < ss[15.0]
    with open(tmp_path / "sweep" / "sweep_summary.csv") as f:
        assert len(list(csv.DictReader(f))) == 2


@pytest.mark.slow
def test_sweep_from_points_csv_end_to_end(tmp_path):
    """CSV design-point import drives the same engine (rows = runs)."""
    cfg = tmp_path / "tiny.yaml"
    cfg.write_text("""
device: {name: sweep_csv, polarity: n, gate_workfunction_ev: 4.5}
mesh: {nx_sd: 6, nx_gate: 10, ny_si: 5, ny_ox: 2}
simulation: {type: idvg, vd: [0.7], vg_start: 0.0, vg_stop: 0.7, vg_step: 0.1}
output: {directory: unused, vtk: false}
""")
    doe = tmp_path / "doe.csv"
    doe.write_text("device.l_gate_nm\n15.0\n21.0\n", encoding="utf-8")
    rows = run_sweep(cfg, None, tmp_path / "sweep", jobs=2,
                     points=load_points_csv(doe))
    assert [r["status"] for r in rows] == ["ok", "ok"]
    ss = {r["device.l_gate_nm"]: r["Vd = +0.70 V.ss_mv_per_dec"]
          for r in rows}
    assert ss[21.0] < ss[15.0]
    # 1D numeric point list gets the trend plot like a zip sweep
    assert (tmp_path / "sweep" / "sweep_trends.png").exists()
