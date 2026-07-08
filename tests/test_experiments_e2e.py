"""End-to-end smoke tests for every experiment type the runner drives,
plus the partial-results-on-convergence-failure contract.  Coarse meshes
and 3-point sweeps keep each solve in the seconds range."""

import csv

import pytest

from cfet_tcad.solve import ConvergenceError
from cfet_tcad.workflow import runner as runner_mod
from cfet_tcad.workflow.config import build_config
from cfet_tcad.workflow.runner import Runner, run_config

COARSE = {"nx_sd": 8, "nx_gate": 12, "ny_si": 6, "ny_ox": 2}


def _read_csv(path):
    with open(path, encoding="utf-8") as f:
        return [{k: float(v) for k, v in row.items()}
                for row in csv.DictReader(f)]


@pytest.mark.slow
def test_run_idvd_end_to_end(tmp_path, fresh_devsim):
    cfg = build_config({
        "device": {"name": "idvd_sm", "polarity": "n",
                   "gate_workfunction_ev": 4.5},
        "mesh": COARSE,
        "simulation": {"type": "idvd", "vg": [0.7],
                       "vd_start": 0.0, "vd_stop": 0.2, "vd_step": 0.1},
        "output": {"vtk": False},
    })
    run_config(cfg, tmp_path)
    rows = _read_csv(tmp_path / "idvd.csv")
    assert len(rows) == 3
    id_a = [r["id_a"] for r in rows]
    # nFET output characteristic: current grows with Vd at fixed Vg
    assert id_a[0] < id_a[1] < id_a[2]
    assert id_a[2] > 0
    assert (tmp_path / "idvd.png").exists()


@pytest.mark.slow
def test_run_cfet_idvg_end_to_end(tmp_path, fresh_devsim):
    cfg = build_config({
        "device": {"name": "cfetg_sm", "structure": "cfet_2d"},
        "mesh": COARSE,
        "simulation": {"type": "cfet_idvg", "vg_start": 0.0,
                       "vg_stop": 0.7, "vg_step": 0.35, "vdd": 0.7},
        "output": {"vtk": False},
    })
    run_config(cfg, tmp_path)
    rows = _read_csv(tmp_path / "cfet_idvg.csv")
    assert len(rows) == 3
    # common-gate sweep: nFET turns on with Vg while the pFET turns off
    assert abs(rows[-1]["id_n_a"]) > 10 * abs(rows[0]["id_n_a"])
    assert abs(rows[0]["id_p_a"]) > 10 * abs(rows[-1]["id_p_a"])
    assert (tmp_path / "fom.json").exists()


@pytest.mark.slow
def test_run_cfet_idvd_end_to_end(tmp_path, fresh_devsim):
    cfg = build_config({
        "device": {"name": "cfetd_sm", "structure": "cfet_2d"},
        "mesh": COARSE,
        "simulation": {"type": "cfet_idvd", "vg": [0.7],
                       "vd_start": 0.0, "vd_stop": 0.35, "vd_step": 0.175,
                       "vdd": 0.7},
        "output": {"vtk": False},
    })
    run_config(cfg, tmp_path)
    rows = _read_csv(tmp_path / "cfet_idvd.csv")
    assert len(rows) == 3
    # at Vg = Vdd the nFET is on: its drain current grows with Vd
    id_n = [abs(r["id_n_a"]) for r in rows]
    assert id_n[0] < id_n[1] < id_n[2]
    # ... while the pFET (Vgs = 0) stays orders of magnitude below it
    assert abs(rows[-1]["id_p_a"]) < id_n[2] / 100
    assert (tmp_path / "cfet_idvd.png").exists()


@pytest.mark.slow
def test_run_cfet_vtc_end_to_end(tmp_path, fresh_devsim):
    cfg = build_config({
        "device": {"name": "vtc_sm", "structure": "cfet_2d"},
        "mesh": COARSE,
        "simulation": {"type": "cfet_vtc", "vg_start": 0.0,
                       "vg_stop": 0.7, "vg_step": 0.1, "vdd": 0.7},
        "output": {"vtk": False},
    })
    run_config(cfg, tmp_path)
    rows = _read_csv(tmp_path / "vtc.csv")
    assert len(rows) == 8
    vout = [r["vout_v"] for r in rows]
    # inverter: output starts near the rail, ends near ground
    assert vout[0] > 0.5 and vout[-1] < 0.2
    assert all(a >= b - 1e-6 for a, b in zip(vout, vout[1:]))  # monotone
    assert (tmp_path / "fom.json").exists()


def test_partial_csv_written_on_convergence_failure(tmp_path, fresh_devsim,
                                                    monkeypatch):
    """A mid-sweep ConvergenceError must leave the already-measured points
    on disk instead of discarding the whole run."""
    cfg = build_config({
        "device": {"name": "partial_sm", "polarity": "n",
                   "gate_workfunction_ev": 4.5},
        "mesh": COARSE,
        "simulation": {"type": "idvg", "vd": [0.05],
                       "vg_start": 0.0, "vg_stop": 0.3, "vg_step": 0.1},
        "output": {"vtk": False},
    })

    calls = {"n": 0}

    def failing_ramp(device, contacts, target, step=0.05, min_step=1e-4,
                     solver_args=None):
        # no-op ramps (the device stays at its solved equilibrium, so
        # measure() still works) until the forced failure
        calls["n"] += 1
        if calls["n"] >= 5:
            raise ConvergenceError("forced mid-sweep failure (test)")

    monkeypatch.setattr(runner_mod, "ramp_biases", failing_ramp)
    with pytest.raises(ConvergenceError, match="forced"):
        Runner(cfg, tmp_path).run()

    # ramps 1-2 position gate/drain, 3 starts the sweep (point 0 measured),
    # ramp 4 reaches point 1, ramp 5 raises -> two completed points saved
    rows = _read_csv(tmp_path / "idvg.csv")
    assert len(rows) == 2


def test_unknown_sim_type_raises_not_falls_through(tmp_path):
    cfg = build_config({"device": {"name": "x"}})
    r = Runner(cfg, tmp_path)
    cfg.simulation.type = "bogus"  # bypass config validation on purpose
    r.build_mesh = lambda: None
    r._validate_sim_contacts = lambda: None
    r.setup = lambda _msh: None
    with pytest.raises(ValueError, match="unknown simulation type"):
        r.run()
