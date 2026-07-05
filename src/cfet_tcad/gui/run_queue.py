"""Process pool driving simulations through the existing CLI.

DEVSIM keeps global state, so every experiment runs in its own OS process
(``python -m cfet_tcad.workflow.cli run <yaml> -o <dir>``), mirroring the
sweep engine.  A bounded number of QProcesses run concurrently; solver
output streams to the log, and fom.json is folded back into the table row
on completion — the SWB node lighting up green.
"""

import json
import os
import sys
from pathlib import Path

import yaml
from PySide6.QtCore import QObject, QProcess, Signal

from ..workflow.config import apply_overrides
from .experiment_table import Experiment, ExperimentModel, fom_summary


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
        self._procs: dict[int, QProcess] = {}  # row -> process

    # --- job creation -------------------------------------------------------

    def make_experiment(self, name: str, base_config: Path, out_dir: Path,
                        overrides: dict | None = None) -> Experiment:
        """Materialize a point config (base YAML + overrides) in its own
        output directory and register it as a queued experiment."""
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        raw = yaml.safe_load(Path(base_config).read_text()) or {}
        if overrides:
            raw = apply_overrides(raw, overrides)
        cfg = out_dir / "config.yaml"
        cfg.write_text(yaml.safe_dump(raw, sort_keys=False))
        return Experiment(name=name, config_path=cfg, out_dir=out_dir,
                          overrides=dict(overrides or {}))

    def enqueue(self, exp: Experiment) -> int:
        row = self.model.add(exp)
        self._maybe_start()
        return row

    # --- scheduling -----------------------------------------------------

    def _maybe_start(self) -> None:
        for row, exp in enumerate(self.model.experiments):
            if len(self._procs) >= self.max_parallel:
                return
            if exp.status == "queued" and row not in self._procs:
                self._start(row, exp)
        if not self._procs:
            self.idle.emit()

    def _start(self, row: int, exp: Experiment) -> None:
        program, prefix = cli_command()
        proc = QProcess(self)
        proc.setProgram(program)
        proc.setArguments(prefix + ["run", str(exp.config_path),
                                    "-o", str(exp.out_dir)])
        proc.setProcessChannelMode(QProcess.MergedChannels)
        proc.readyReadStandardOutput.connect(
            lambda r=row, p=proc: self._on_output(r, p))
        proc.finished.connect(
            lambda code, _status, r=row: self._on_finished(r, code))
        self._procs[row] = proc
        exp.status = "running"
        self.model.update_row(row)
        self.experiment_changed.emit(row)
        self.log_line.emit(f"[{exp.name}] started")
        proc.start()

    def _on_output(self, row: int, proc: QProcess) -> None:
        name = self.model.experiments[row].name
        text = bytes(proc.readAllStandardOutput()).decode(errors="replace")
        for line in text.splitlines():
            self.log_line.emit(f"[{name}] {line}")

    def _on_finished(self, row: int, exit_code: int) -> None:
        exp = self.model.experiments[row]
        self._procs.pop(row, None)
        exp.status = "done" if exit_code == 0 else "failed"
        if exit_code == 0:
            fom_path = exp.out_dir / "fom.json"
            if fom_path.exists():
                exp.fom = fom_summary(json.loads(fom_path.read_text()))
        self.model.update_row(row)
        self.experiment_changed.emit(row)
        self.log_line.emit(f"[{exp.name}] {exp.status} (exit {exit_code})")
        self._maybe_start()

    def stop_all(self) -> None:
        for row, proc in list(self._procs.items()):
            proc.kill()
            self.model.experiments[row].status = "failed"
            self.model.update_row(row)
        self._procs.clear()
        for exp in self.model.experiments:
            if exp.status == "queued":
                exp.status = "failed"
        self.model.layoutChanged.emit()
