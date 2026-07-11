"""GUI surface for the LLM device-parameter optimizer: a setup dialog
(objective / candidate-count / provider) and a non-modal progress/results
monitor, built almost entirely from existing pieces (ExperimentModel,
RunQueue's status colors, ParamsDialog's Save-As) plus the orchestrator.
"""

from pathlib import Path

from PySide6.QtCore import QModelIndex, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..optimize.objective import CONSTRAINT_OPS, ObjectiveSpec, ObjectiveTerm
from ..optimize.orchestrator import OptimizeSpec, Orchestrator
from .experiment_table import COLUMNS, ExperimentModel
from .params_dialog import ParamsDialog


def _parse_constraint(text: str) -> tuple:
    parts = text.split(None, 1)
    if len(parts) != 2:
        raise ValueError(
            f"constraint {text!r} must be 'OP VALUE', e.g. '< 75'")
    op, value = parts
    if op not in CONSTRAINT_OPS:
        raise ValueError(
            f"constraint op must be one of {sorted(CONSTRAINT_OPS)}, "
            f"got {op!r}")
    try:
        value = float(value)
    except ValueError:
        raise ValueError(
            f"constraint value {value!r} is not numeric") from None
    return (op, value)


class ObjectiveEditor(QWidget):
    """Metric / Direction / Constraint rows -> ObjectiveSpec (v1 keeps the
    per-term weight at its dataclass default; no weight column here)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(
            ["Metric", "Direction", "Constraint (optional, e.g. < 75)"])
        self.table.horizontalHeader().setStretchLastSection(True)
        add_btn = QPushButton("+ term")
        add_btn.clicked.connect(lambda: self.add_row())
        remove_btn = QPushButton("- term")
        remove_btn.clicked.connect(self._remove_selected)
        bar = QHBoxLayout()
        bar.addWidget(add_btn)
        bar.addWidget(remove_btn)
        bar.addStretch(1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.table)
        layout.addLayout(bar)
        self.add_row("ion_ioff_ratio", "maximize")

    def add_row(self, metric: str = "", direction: str = "maximize",
               constraint: str = "") -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(metric))
        combo = QComboBox()
        combo.addItems(["maximize", "minimize"])
        combo.setCurrentText(direction)
        self.table.setCellWidget(row, 1, combo)
        self.table.setItem(row, 2, QTableWidgetItem(constraint))

    def _remove_selected(self) -> None:
        rows = sorted({i.row() for i in self.table.selectedIndexes()},
                     reverse=True)
        for row in rows:
            self.table.removeRow(row)

    def to_spec(self) -> ObjectiveSpec:
        """Raises ValueError (via ObjectiveTerm/ObjectiveSpec/
        _parse_constraint) on any malformed or empty row set."""
        terms = []
        for row in range(self.table.rowCount()):
            metric_item = self.table.item(row, 0)
            metric = metric_item.text().strip() if metric_item else ""
            if not metric:
                continue
            direction = self.table.cellWidget(row, 1).currentText()
            constraint_item = self.table.item(row, 2)
            constraint_text = (constraint_item.text().strip()
                               if constraint_item else "")
            constraint = (_parse_constraint(constraint_text)
                         if constraint_text else None)
            terms.append(ObjectiveTerm(metric=metric, direction=direction,
                                       constraint=constraint))
        return ObjectiveSpec(terms=terms)  # raises ValueError if empty


class OptimizeSetupDialog(QDialog):
    """Modal (short-lived, like SweepDialog): configure one optimization
    run.  ``provider_factories`` maps a display name to a zero-arg
    callable returning an LLMProvider; the caller (MainWindow) decides
    what's on offer so this module never imports a concrete vendor."""

    def __init__(self, base_config: Path, provider_factories: dict,
                parent=None):
        super().__init__(parent)
        self.base_config = Path(base_config)
        self.provider_factories = provider_factories
        self.setWindowTitle(f"Optimize - {self.base_config.name}")

        self.objective_editor = ObjectiveEditor()
        self.n_candidates = QSpinBox()
        self.n_candidates.setRange(1, 16)
        self.n_candidates.setValue(4)
        self.max_rounds = QSpinBox()
        self.max_rounds.setRange(1, 50)
        self.max_rounds.setValue(8)
        self.max_parallel = QSpinBox()
        self.max_parallel.setRange(1, 16)
        self.max_parallel.setValue(4)
        self.provider_box = QComboBox()
        self.provider_box.addItems(list(provider_factories))
        self.provider_box.setEnabled(bool(provider_factories))

        form = QFormLayout()
        form.addRow(QLabel(f"Base design: {self.base_config.name}"))
        form.addRow("objective", self.objective_editor)
        form.addRow("candidates / round", self.n_candidates)
        form.addRow("max rounds", self.max_rounds)
        form.addRow("max parallel", self.max_parallel)
        form.addRow("LLM provider", self.provider_box)
        if not provider_factories:
            form.addRow(QLabel(
                "No LLM provider available - install the [llm] extra."))

        buttons = QDialogButtonBox(QDialogButtonBox.Ok
                                   | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

        #: populated on successful accept(); None otherwise
        self.result_spec: OptimizeSpec | None = None
        self.result_provider = None

    def _on_accept(self) -> None:
        if not self.provider_factories:
            QMessageBox.warning(self, "No provider",
                                "No LLM provider is available.")
            return
        try:
            objective = self.objective_editor.to_spec()
        except ValueError as exc:
            QMessageBox.warning(self, "Objective error", str(exc))
            return
        try:
            provider = self.provider_factories[
                self.provider_box.currentText()]()
        except Exception as exc:  # noqa: BLE001 - provider construction
            QMessageBox.warning(self, "Provider error", str(exc))
            return
        try:
            self.result_spec = OptimizeSpec(
                base_config=self.base_config, objective=objective,
                n_candidates=self.n_candidates.value(),
                max_rounds=self.max_rounds.value(),
                max_parallel=self.max_parallel.value())
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid settings", str(exc))
            return
        self.result_provider = provider
        self.accept()


class OptimizeExperimentModel(ExperimentModel):
    """ExperimentModel + a read-only Score column, read live from the
    owning Orchestrator's ``exp_scores`` (kept off the shared Experiment
    dataclass, which the main window's own table also uses)."""

    def __init__(self, orchestrator: Orchestrator, parent=None):
        super().__init__(parent)
        self.orchestrator = orchestrator

    def columnCount(self, parent=QModelIndex()):
        return super().columnCount(parent) + 1

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if (orientation == Qt.Horizontal and role == Qt.DisplayRole
                and section == len(COLUMNS)):
            return "Score"
        return super().headerData(section, orientation, role)

    def data(self, index, role=Qt.DisplayRole):
        if index.column() == len(COLUMNS):
            if role != Qt.DisplayRole or not index.isValid():
                return None
            exp = self.experiments[index.row()]
            score = self.orchestrator.exp_scores.get(exp)
            return f"{score:.4g}" if score is not None else ""
        return super().data(index, role)

    def refresh_scores(self) -> None:
        """Repaint the Score column after the orchestrator updates it
        (e.g. on every round_completed -- scores get rescored as the run's
        normalization ranges grow, so more than just the latest row can
        change)."""
        if not self.experiments:
            return
        top_left = self.index(0, len(COLUMNS))
        bottom_right = self.index(len(self.experiments) - 1, len(COLUMNS))
        self.dataChanged.emit(top_left, bottom_right)


class OptimizeMonitorDialog(QDialog):
    """Non-modal: an optimization run can take many rounds/minutes, and
    the user should be able to keep using the main window meanwhile --
    every other dialog in this codebase is modal (.exec()); this is a
    deliberate, single exception."""

    def __init__(self, orchestrator: Orchestrator, configs_dir: Path,
                parent=None):
        super().__init__(parent)
        self.orchestrator = orchestrator
        self.configs_dir = Path(configs_dir)
        self.setWindowTitle(
            f"Optimizing - {orchestrator.spec.base_config.name}")
        self.setModal(False)

        self.status_label = QLabel("starting...")
        self.best_label = QLabel("best so far: (none yet)")
        self.table = QTableView()
        self.table.setModel(orchestrator.model)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.clicked.connect(self.orchestrator.stop)
        self.adopt_btn = QPushButton("Adopt best...")
        self.adopt_btn.setEnabled(False)
        self.adopt_btn.clicked.connect(self._adopt_best)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)

        bar = QHBoxLayout()
        bar.addWidget(self.stop_btn)
        bar.addWidget(self.adopt_btn)
        bar.addStretch(1)
        bar.addWidget(close_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(self.status_label)
        layout.addWidget(self.table, stretch=1)
        layout.addWidget(self.best_label)
        layout.addLayout(bar)
        self.resize(900, 500)

        orchestrator.status_message.connect(self.status_label.setText)
        orchestrator.round_completed.connect(self._on_round_completed)
        orchestrator.finished.connect(self._on_finished)

    def _on_round_completed(self, _round_index: int) -> None:
        if hasattr(self.orchestrator.model, "refresh_scores"):
            self.orchestrator.model.refresh_scores()
        best = self.orchestrator.best
        if best is not None:
            self.best_label.setText(
                f"best so far: score={best.score:.4g}  {best.overrides}")
            self.adopt_btn.setEnabled(True)

    def _on_finished(self, reason: str) -> None:
        self.status_label.setText(f"finished: {reason}")
        self.stop_btn.setEnabled(False)

    def _adopt_best(self) -> None:
        """Save the best candidate's config as a new reusable design --
        identical mechanism to MainWindow.edit_experiment()'s Save-As."""
        exp = self.orchestrator.best_experiment
        if exp is None:
            return
        stem = self.orchestrator.spec.base_config.stem
        try:
            dlg = ParamsDialog(exp.config_path, parent=self,
                               save_as_dir=self.configs_dir,
                               save_as_name=f"{stem}_optimized")
        except Exception as exc:  # noqa: BLE001 - malformed YAML etc.
            QMessageBox.warning(self, "Config error", str(exc))
            return
        dlg.exec()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self.orchestrator.is_running:
            answer = QMessageBox.question(
                self, "Stop optimization?",
                "The optimization run is still active. Stop it and "
                "close this window?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if answer != QMessageBox.Yes:
                event.ignore()
                return
        self.orchestrator.stop()
        super().closeEvent(event)
