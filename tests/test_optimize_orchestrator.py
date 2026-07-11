"""End-to-end orchestrator tests: real RunQueue + a fake CLI subprocess
(no DEVSIM) + FakeProvider, driven entirely through Qt signals -- the
same idiom as tests/test_gui.py's live-QProcess tests."""

import os
import sys
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from cfet_tcad.gui import run_queue as rq  # noqa: E402
from cfet_tcad.optimize.llm_provider import (  # noqa: E402
    CandidateProposal,
    FakeProvider,
)
from cfet_tcad.optimize.objective import ObjectiveSpec, ObjectiveTerm  # noqa: E402
from cfet_tcad.optimize.orchestrator import Orchestrator, OptimizeSpec  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


# A candidate's l_gate_nm drives a deterministic fake FOM so tests can
# assert on which candidate "wins" -- no DEVSIM/gmsh involved.
FAKE_CLI_SCRIPT = """
import json, os, sys
import yaml
args = sys.argv[1:]
out = args[args.index("-o") + 1]
cfg_path = args[1]
os.makedirs(out, exist_ok=True)
raw = yaml.safe_load(open(cfg_path)) or {}
l_gate = float((raw.get("device") or {}).get("l_gate_nm", 15.0))
fom = {"ion_ioff_ratio": 1e4 + l_gate * 1000.0,
      "ss_mv_per_dec": 90.0 - l_gate}
json.dump(fom, open(os.path.join(out, "fom.json"), "w"))
print("@@PROGRESS 1/1", flush=True)
"""


def _pump(qapp, predicate, timeout_s=20.0):
    """Process Qt events until predicate() is true or timeout."""
    deadline = time.time() + timeout_s
    while not predicate() and time.time() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    assert predicate(), "timed out waiting for condition"


@pytest.fixture()
def orchestrator(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(rq, "cli_command",
                        lambda: (sys.executable, ["-c", FAKE_CLI_SCRIPT]))
    base = tmp_path / "base.yaml"
    base.write_text("device:\n  name: opt_base\n  l_gate_nm: 15.0\n")
    spec = OptimizeSpec(
        base_config=base,
        objective=ObjectiveSpec(terms=[
            ObjectiveTerm(metric="ion_ioff_ratio", direction="maximize"),
        ]),
        n_candidates=2, max_rounds=2, max_parallel=2,
        total_wall_clock_budget_s=None)
    yield spec, tmp_path / "out"


def test_two_rounds_batch_then_max_rounds_stopping(qapp, orchestrator):
    spec, out_dir = orchestrator
    round1 = [CandidateProposal(overrides={"device.l_gate_nm": 12.0}),
             CandidateProposal(overrides={"device.l_gate_nm": 20.0})]
    round2 = [CandidateProposal(overrides={"device.l_gate_nm": 30.0}),
             CandidateProposal(overrides={"device.l_gate_nm": 18.0})]
    provider = FakeProvider(responses=[round1, round2])
    orch = Orchestrator(spec, provider, out_dir)

    events = {"rounds_started": [], "rounds_completed": [], "finished": None}
    orch.round_started.connect(lambda i: events["rounds_started"].append(i))
    orch.round_completed.connect(lambda i: events["rounds_completed"].append(i))
    orch.finished.connect(lambda r: events.__setitem__("finished", r))

    orch.start()
    _pump(qapp, lambda: events["finished"] is not None)

    assert events["finished"] == "max_rounds"
    assert events["rounds_started"] == [1, 2]
    assert events["rounds_completed"] == [1, 2]
    assert len(orch.history) == 4
    assert all(r.status == "done" for r in orch.history)
    # maximize ion_ioff_ratio, which scales with l_gate_nm in the fake
    # CLI -- round 2's l_gate_nm=30 candidate must win
    assert orch.best is not None
    assert orch.best.overrides["device.l_gate_nm"] == 30.0

    # no orphaned subprocess or thread once the run has finished
    assert not orch.queue._procs
    assert not orch._thread.isRunning()


def test_invalid_candidate_repairs_within_round_no_subprocess(qapp,
                                                              orchestrator):
    spec, out_dir = orchestrator
    spec.n_candidates = 1
    spec.max_rounds = 1
    out_of_bounds = CandidateProposal(overrides={"device.l_gate_nm": 999.0})
    repaired = CandidateProposal(overrides={"device.l_gate_nm": 20.0})
    provider = FakeProvider(responses=[[out_of_bounds], [repaired]])
    orch = Orchestrator(spec, provider, out_dir)

    finished = {}
    orch.finished.connect(lambda r: finished.__setitem__("reason", r))
    orch.start()
    _pump(qapp, lambda: "reason" in finished)

    assert finished["reason"] == "max_rounds"
    # exactly one experiment ever got materialized/run - the repaired one
    assert len(orch.model.experiments) == 1
    assert orch.model.experiments[0].overrides["device.l_gate_nm"] == 20.0
    # the repair call carried the rejection reason back to the provider
    assert len(provider.calls) == 2
    repair_context = provider.calls[1]["repair_context"]
    assert repair_context is not None
    assert "l_gate_nm" in repair_context
    # the rejected candidate is recorded in history too (for future
    # rounds' context) even though it never ran
    rejected = [r for r in orch.history if r.status.startswith("rejected")]
    assert len(rejected) == 1
    assert rejected[0].overrides["device.l_gate_nm"] == 999.0


def test_zero_valid_candidates_after_repairs_aborts_on_cap(qapp,
                                                           orchestrator):
    spec, out_dir = orchestrator
    spec.n_candidates = 1
    spec.max_repairs_per_round = 1
    spec.max_validation_failed_rounds = 2
    bad = CandidateProposal(overrides={"device.l_gate_nm": 999.0})
    # every attempt (initial + 1 repair, x2 rounds worth) is invalid
    provider = FakeProvider(responses=[[bad], [bad], [bad], [bad]])
    orch = Orchestrator(spec, provider, out_dir)

    finished = {}
    orch.finished.connect(lambda r: finished.__setitem__("reason", r))
    orch.start()
    _pump(qapp, lambda: "reason" in finished)

    assert finished["reason"] == "validation_failed"
    assert not orch.model.experiments  # nothing ever ran
    assert not orch.queue._procs
    assert not orch._thread.isRunning()


def test_stop_mid_run_leaves_no_orphans(qapp, orchestrator, monkeypatch):
    spec, out_dir = orchestrator
    spec.n_candidates = 1
    # slow fake CLI so we can call stop() while a candidate is running
    slow_script = FAKE_CLI_SCRIPT.replace(
        "print(\"@@PROGRESS 1/1\", flush=True)",
        "import time; time.sleep(30)")
    monkeypatch.setattr(rq, "cli_command",
                        lambda: (sys.executable, ["-c", slow_script]))

    provider = FakeProvider(
        responses=[[CandidateProposal(overrides={"device.l_gate_nm": 20.0})]])
    orch = Orchestrator(spec, provider, out_dir)
    finished = {}
    orch.finished.connect(lambda r: finished.__setitem__("reason", r))
    orch.start()
    _pump(qapp, lambda: bool(orch.model.experiments)
         and orch.model.experiments[0].status == "running")

    orch.stop()
    _pump(qapp, lambda: "reason" in finished)
    assert finished["reason"] == "stopped"
    assert not orch.queue._procs
    assert not orch._thread.isRunning()
