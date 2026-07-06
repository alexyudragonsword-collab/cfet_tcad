"""Process pool driving simulations through the existing CLI.

DEVSIM keeps global state, so every experiment runs in its own OS process
(``python -m cfet_tcad.workflow.cli run <yaml> -o <dir>``), mirroring the
sweep engine.  A bounded number of QProcesses run concurrently; solver
output streams to the log, and fom.json is folded back into the table row
on completion — the SWB node lighting up green.
"""

import json
import os
import re
import sys
from pathlib import Path

import yaml
from PySide6.QtCore import QObject, QProcess, Signal

from ..workflow.config import apply_overrides, resolve_external_mesh
from .experiment_table import Experiment, ExperimentModel, fom_summary


_PROGRESS_RE = re.compile(r"^@@PROGRESS (\d+)/(\d+)\s*$")


def parse_progress_line(line: str):
    """'@@PROGRESS 3/29' -> (3, 29); None for anything else."""
    m = _PROGRESS_RE.match(line)
    return (int(m.group(1)), int(m.group(2))) if m else None


def cli_command() -> tuple[str, list[str]]:
    """(program, prefix args) that invoke the cfet-tcad CLI in a child
    process.  Frozen (PyInstaller) builds have no Python interpreter —
    ``sys.executable`` is the GUI exe itself — so they call the bundled
    CLI executable sitting next to it instead of ``python -m``."""
    if getattr(sys, "frozen", False):
        name = "cfet-tcad.exe" if os.name == "nt" else "cfet-tcad"
        sibling = Path(sys.executable).with_name(name)
        if sibling.exists():
            return str(sibling), []
        # single-exe dispatcher bundles (Nuitka): the same executable
        # acts as the CLI when given arguments
        return sys.executable, []
    return sys.executable, ["-m", "cfet_tcad.workflow.cli"]


class RunQueue(QObject):
    log_line = Signal(str)
    experiment_changed = Signal(int)  # row index
    idle = Signal()

    def __init__(self, model: ExperimentModel, max_parallel: int = 2,
                 parent=None):
        super().__init__(parent)
        self.model = model
        self.max_parallel = max_parallel
        # keyed by Experiment identity, never by row: removing a table
        # row shifts every following row index
        self._procs: dict[Experiment, QProcess] = {}

    # --- job creation -------------------------------------------------------

    def make_experiment(self, name: str, base_config: Path, out_dir: Path,
                        overrides: dict | None = None) -> Experiment:
        """Materialize a point config (base YAML + overrides) in its own
        output directory and register it as a queued experiment."""
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        raw = yaml.safe_load(
            Path(base_config).read_text(encoding="utf-8")) or {}
        if overrides:
            raw = apply_overrides(raw, overrides)
        # the point config lands in out_dir: pin a relative external mesh
        # to the base config's directory before the copy moves it
        resolve_external_mesh(raw, Path(base_config).parent)
        cfg = out_dir / "config.yaml"
        cfg.write_text(yaml.safe_dump(raw, sort_keys=False),
                       encoding="utf-8")
        return Experiment(name=name, config_path=cfg, out_dir=out_dir,
                          overrides=dict(overrides or {}))

    def add(self, exp: Experiment) -> int:
        """Register an experiment in the table as *pending*: it will not
        run until its own Run button (or Run All) starts it."""
        return self.model.add(exp)

    def start(self, exp: Experiment) -> None:
        """(Re)start one experiment.  Finished/stopped/failed rows requeue
        in place: same row, same out_dir, previous results overwritten."""
        if exp.status in ("queued", "running"):
            return
        exp.status = "queued"
        exp.progress = None
        exp.fom = {}
        self._touch(exp)
        self._maybe_start()

    def run_all(self) -> None:
        """Start every pending/stopped/failed experiment.  Finished (done)
        rows are left alone - rerunning those is a per-row decision."""
        for exp in list(self.model.experiments):
            if exp.status in ("pending", "stopped", "failed"):
                self.start(exp)

    # --- scheduling -----------------------------------------------------

    def _maybe_start(self) -> None:
        for exp in self.model.experiments:
            if len(self._procs) >= self.max_parallel:
                return
            if exp.status == "queued" and exp not in self._procs:
                self._start(exp)
        if not self._procs:
            self.idle.emit()

    def _touch(self, exp: Experiment) -> None:
        row = self.model.row_of(exp)
        self.model.update_row(row)
        self.experiment_changed.emit(row)

    def _start(self, exp: Experiment) -> None:
        program, prefix = cli_command()
        proc = QProcess(self)
        proc.setProgram(program)
        proc.setArguments(prefix + ["run", str(exp.config_path),
                                    "-o", str(exp.out_dir)])
        proc.setProcessChannelMode(QProcess.MergedChannels)
        proc.readyReadStandardOutput.connect(
            lambda e=exp, p=proc: self._on_output(e, p))
        proc.finished.connect(
            lambda code, _status, e=exp: self._on_finished(e, code))
        self._procs[exp] = proc
        exp.status = "running"
        self._touch(exp)
        self.log_line.emit(f"[{exp.name}] started")
        proc.start()

    def _on_output(self, exp: Experiment, proc: QProcess) -> None:
        text = bytes(proc.readAllStandardOutput()).decode(errors="replace")
        for line in text.splitlines():
            progress = parse_progress_line(line)
            if progress is not None:  # swallowed: table cell, not log spam
                done, total = progress
                exp.progress = done / total if total else None
                self._touch(exp)
                continue
            self.log_line.emit(f"[{exp.name}] {line}")

    def _on_finished(self, exp: Experiment, exit_code: int) -> None:
        self._procs.pop(exp, None)
        if exp.status != "stopped":  # a stop() stays a stop, not a failure
            exp.status = "done" if exit_code == 0 else "failed"
        if exit_code == 0:
            fom_path = exp.out_dir / "fom.json"
            if fom_path.exists():
                exp.fom = fom_summary(
                    json.loads(fom_path.read_text(encoding="utf-8")))
        self._touch(exp)
        self.log_line.emit(f"[{exp.name}] {exp.status} (exit {exit_code})")
        self._maybe_start()

    def stop(self, exp: Experiment) -> None:
        """Stop one experiment: kill its process if running, or take a
        queued one out of the schedule.  Files already written remain."""
        if exp.status not in ("queued", "running"):
            return
        exp.status = "stopped"
        proc = self._procs.get(exp)
        if proc is not None:
            proc.kill()  # _on_finished keeps the "stopped" status
        else:
            self._touch(exp)
            self.log_line.emit(f"[{exp.name}] stopped (was queued)")

    def stop_all(self) -> None:
        for exp in list(self.model.experiments):
            self.stop(exp)
