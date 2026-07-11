"""GUI tests for the Optimize dialogs: objective editor, setup dialog,
the Score-column model, and an end-to-end monitor-dialog run against a
fake CLI subprocess + FakeProvider (no DEVSIM, no network) -- same idiom
as tests/test_gui.py's live-QProcess tests."""

import os
import sys
import time
import types

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QDialog, QMessageBox  # noqa: E402

from cfet_tcad.gui import run_queue as rq  # noqa: E402
from cfet_tcad.gui.experiment_table import COLUMNS, Experiment  # noqa: E402
from cfet_tcad.gui.optimize_dialog import (  # noqa: E402
    ObjectiveEditor,
    OptimizeExperimentModel,
    OptimizeMonitorDialog,
    OptimizeSetupDialog,
)
from cfet_tcad.optimize.llm_provider import CandidateProposal, FakeProvider  # noqa: E402
from cfet_tcad.optimize.orchestrator import Orchestrator, OptimizeSpec  # noqa: E402
from cfet_tcad.optimize.objective import ObjectiveSpec, ObjectiveTerm  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


FAKE_CLI_SCRIPT = """
import json, os, sys
import yaml
args = sys.argv[1:]
out = args[args.index("-o") + 1]
cfg_path = args[1]
os.makedirs(out, exist_ok=True)
raw = yaml.safe_load(open(cfg_path)) or {}
l_gate = float((raw.get("device") or {}).get("l_gate_nm", 15.0))
json.dump({"ion_ioff_ratio": 1e4 + l_gate * 1000.0},
         open(os.path.join(out, "fom.json"), "w"))
"""


def _pump(qapp, predicate, timeout_s=20.0):
    deadline = time.time() + timeout_s
    while not predicate() and time.time() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    assert predicate(), "timed out waiting for condition"


# --- ObjectiveEditor --------------------------------------------------

def test_objective_editor_default_row_and_roundtrip(qapp):
    editor = ObjectiveEditor()
    spec = editor.to_spec()
    assert len(spec.terms) == 1
    assert spec.terms[0].metric == "ion_ioff_ratio"
    assert spec.terms[0].direction == "maximize"
    assert spec.terms[0].constraint is None


def test_objective_editor_constraint_and_blank_row_skipped(qapp):
    editor = ObjectiveEditor()
    editor.add_row("ss_mv_per_dec", "minimize", "< 75")
    editor.add_row("", "maximize", "")  # blank metric: silently skipped
    spec = editor.to_spec()
    assert len(spec.terms) == 2
    assert spec.terms[1].constraint == ("<", 75.0)


def test_objective_editor_bad_constraint_raises(qapp):
    editor = ObjectiveEditor()
    editor.add_row("ion_a", "maximize", "not-a-constraint")
    with pytest.raises(ValueError, match="OP VALUE"):
        editor.to_spec()


def test_objective_editor_empty_raises(qapp):
    editor = ObjectiveEditor()
    editor.table.removeRow(0)  # drop the default row: no terms left
    with pytest.raises(ValueError):
        editor.to_spec()


# --- OptimizeSetupDialog -----------------------------------------------

def test_setup_dialog_warns_with_no_provider(qapp, tmp_path, monkeypatch):
    base = tmp_path / "base.yaml"
    base.write_text("device: {name: x}\n")
    dlg = OptimizeSetupDialog(base, {}, parent=None)
    warned = {}
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: warned.setdefault("hit", True)))
    dlg._on_accept()
    assert warned.get("hit")
    assert dlg.result_spec is None


def test_setup_dialog_accepts_with_fake_provider(qapp, tmp_path):
    base = tmp_path / "base.yaml"
    base.write_text("device: {name: x}\n")
    dlg = OptimizeSetupDialog(base, {"Fake": lambda: FakeProvider([])}, None)
    dlg.n_candidates.setValue(3)
    dlg.max_rounds.setValue(5)
    dlg._on_accept()
    assert dlg.result_spec is not None
    assert dlg.result_spec.n_candidates == 3
    assert dlg.result_spec.max_rounds == 5
    assert isinstance(dlg.result_provider, FakeProvider)


def test_setup_dialog_empty_objective_blocks_accept(qapp, tmp_path,
                                                    monkeypatch):
    base = tmp_path / "base.yaml"
    base.write_text("device: {name: x}\n")
    dlg = OptimizeSetupDialog(base, {"Fake": lambda: FakeProvider([])}, None)
    dlg.objective_editor.table.removeRow(0)
    warned = {}
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: warned.setdefault("hit", True)))
    dlg._on_accept()
    assert warned.get("hit")
    assert dlg.result_spec is None


# --- OptimizeExperimentModel --------------------------------------------

def test_score_column_reads_live_from_orchestrator_stub(qapp, tmp_path):
    stub = types.SimpleNamespace(exp_scores={})
    model = OptimizeExperimentModel(stub)
    exp = Experiment(name="c0", config_path=tmp_path / "c.yaml",
                     out_dir=tmp_path)
    model.add(exp)
    score_col = len(COLUMNS)
    assert model.headerData(score_col, Qt.Horizontal) == "Score"
    idx = model.index(0, score_col)
    assert model.data(idx) == ""  # no score yet
    stub.exp_scores[exp] = 0.4213
    model.refresh_scores()
    assert model.data(idx) == "0.4213"


# --- OptimizeMonitorDialog end-to-end ------------------------------------

@pytest.fixture()
def base_config(tmp_path):
    base = tmp_path / "base.yaml"
    base.write_text("device:\n  name: opt_base\n  l_gate_nm: 15.0\n")
    return base


def test_monitor_dialog_updates_table_and_adopt(qapp, tmp_path, base_config,
                                                monkeypatch):
    monkeypatch.setattr(rq, "cli_command",
                        lambda: (sys.executable, ["-c", FAKE_CLI_SCRIPT]))
    spec = OptimizeSpec(
        base_config=base_config,
        objective=ObjectiveSpec(terms=[
            ObjectiveTerm(metric="ion_ioff_ratio", direction="maximize")]),
        n_candidates=2, max_rounds=1, max_parallel=2,
        total_wall_clock_budget_s=None)
    provider = FakeProvider(responses=[[
        CandidateProposal(overrides={"device.l_gate_nm": 12.0}),
        CandidateProposal(overrides={"device.l_gate_nm": 20.0}),
    ]])
    orch = Orchestrator(
        spec, provider, tmp_path / "out",
        model_factory=lambda o: OptimizeExperimentModel(o, parent=o))
    dialog = OptimizeMonitorDialog(orch, configs_dir=tmp_path, parent=None)
    assert dialog.table.model() is orch.model

    finished = {}
    orch.finished.connect(lambda r: finished.__setitem__("reason", r))
    orch.start()
    _pump(qapp, lambda: "reason" in finished)

    assert finished["reason"] == "max_rounds"
    assert len(orch.model.experiments) == 2
    assert dialog.adopt_btn.isEnabled()
    assert "score=" in dialog.best_label.text()

    # Adopt best: capture the ParamsDialog instead of exec()-ing it
    from cfet_tcad.gui import optimize_dialog as od
    opened = {}

    def fake_exec(self):
        opened["dlg"] = self
        return QDialog.Accepted
    monkeypatch.setattr(od.ParamsDialog, "exec", fake_exec)
    dialog._adopt_best()
    pdlg = opened["dlg"]
    assert pdlg.path == orch.best_experiment.config_path
    assert pdlg.save_as_dir == tmp_path
    assert pdlg.save_as_name == "base_optimized"

    dialog.close()
    for _ in range(3):
        qapp.processEvents()
    assert not orch.queue._procs
    assert not orch._thread.isRunning()


def test_monitor_dialog_close_mid_run_stops_orchestrator(qapp, tmp_path,
                                                         base_config,
                                                         monkeypatch):
    slow_script = FAKE_CLI_SCRIPT + "\nimport time; time.sleep(30)\n"
    monkeypatch.setattr(rq, "cli_command",
                        lambda: (sys.executable, ["-c", slow_script]))
    spec = OptimizeSpec(
        base_config=base_config,
        objective=ObjectiveSpec(terms=[
            ObjectiveTerm(metric="ion_ioff_ratio", direction="maximize")]),
        n_candidates=1, max_rounds=1, max_parallel=1,
        total_wall_clock_budget_s=None)
    provider = FakeProvider(responses=[[
        CandidateProposal(overrides={"device.l_gate_nm": 20.0})]])
    orch = Orchestrator(
        spec, provider, tmp_path / "out",
        model_factory=lambda o: OptimizeExperimentModel(o, parent=o))
    dialog = OptimizeMonitorDialog(orch, configs_dir=tmp_path, parent=None)
    orch.start()
    _pump(qapp, lambda: bool(orch.model.experiments)
         and orch.model.experiments[0].status == "running")

    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.Yes))
    dialog.close()
    for _ in range(3):
        qapp.processEvents()
    assert not orch.is_running
    assert not orch.queue._procs
    assert not orch._thread.isRunning()
