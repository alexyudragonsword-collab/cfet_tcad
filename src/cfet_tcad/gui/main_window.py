"""Main window: Sentaurus Workbench-style layout.

Left: config browser.  Center tabs: Experiments (node table), Parameters
(config form), Results (curves + FOMs), Structure 3D.  Bottom: log
console.  Toolbar drives runs and sweeps through the RunQueue; the Help
menu (top-left) opens the user guide window and the About dialog.
"""

import time
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QListWidget,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QSpinBox,
    QSplitter,
    QTableView,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
)

import cfet_tcad

from ..workflow.sweep import parse_param_spec
from .about_dialog import AboutDialog
from .config_form import ConfigForm
from .experiment_table import ExperimentModel
from .help_view import HelpView
from .log_console import LogConsole
from .results_view import ResultsView
from .run_queue import RunQueue
from .structure_view import StructureView


class SweepDialog(QDialog):
    """Parameter specs, one per line: path=v1,v2,... (SWB experiment grid)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New sweep")
        self.specs = QPlainTextEdit()
        self.specs.setPlaceholderText(
            "device.l_gate_nm=12,15,18\n"
            "physics.mobility_model=doping_vsat,lombardi_vsat")
        self.zip_box = QCheckBox("zip (advance lists together)")
        self.jobs = QSpinBox()
        self.jobs.setRange(1, 16)
        self.jobs.setValue(2)
        form = QFormLayout(self)
        form.addRow("parameters", self.specs)
        form.addRow("", self.zip_box)
        form.addRow("max parallel", self.jobs)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok
                                   | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)


class MainWindow(QMainWindow):
    def __init__(self, project_root: Path | None = None):
        super().__init__()
        self.setWindowTitle(f"cfet_tcad workbench v{cfet_tcad.__version__}")
        self.resize(1280, 800)
        self.project_root = Path(project_root or Path.cwd())
        self.results_root = self.project_root / "results" / "gui"

        # widgets
        self.config_list = QListWidget()
        self.model = ExperimentModel(self)
        self.queue = RunQueue(self.model, parent=self)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.form = ConfigForm()
        self.results = ResultsView()
        self.log = LogConsole()

        self.structure = StructureView()
        # the user guide lives in its own window, reached from the Help
        # menu (top-left) — not duplicated as a center tab
        self.help = HelpView()
        self.help.setWindowTitle("User Guide / 用户指南")
        self.help.resize(920, 720)
        self.tabs = QTabWidget()
        self.tabs.addTab(self.table, "Experiments")
        self.tabs.addTab(self.form, "Parameters")
        self.tabs.addTab(self.results, "Results")
        self.tabs.addTab(self.structure, "Structure 3D")

        hsplit = QSplitter(Qt.Horizontal)
        hsplit.addWidget(self.config_list)
        hsplit.addWidget(self.tabs)
        hsplit.setStretchFactor(0, 1)
        hsplit.setStretchFactor(1, 4)
        vsplit = QSplitter(Qt.Vertical)
        vsplit.addWidget(hsplit)
        vsplit.addWidget(self.log)
        vsplit.setStretchFactor(0, 4)
        vsplit.setStretchFactor(1, 1)
        self.setCentralWidget(vsplit)

        # toolbar
        bar = QToolBar("main")
        bar.setMovable(False)
        self.addToolBar(bar)
        bar.addAction("Run", self.run_current)
        bar.addAction("Sweep...", self.run_sweep)
        bar.addAction("Stop", self.queue.stop_all)
        bar.addSeparator()
        bar.addAction("Structure", self.preview_structure)
        bar.addAction("Open config folder...", self.pick_folder)

        # menu bar: single Help entry point at the top-left.  Construct
        # the QMenu with an explicit parent instead of addMenu(str):
        # shiboken deletes the C++ menu of the string overload once the
        # temporary wrapper from menuBar().actions() is garbage collected
        self.help_menu = QMenu("&Help", self)
        self.help_menu.addAction("User Guide / 用户指南", self.show_help)
        self.help_menu.addAction("About cfet_tcad", self.show_about)
        self.menuBar().addMenu(self.help_menu)

        # wiring
        self.config_list.currentTextChanged.connect(self.load_config)
        self.table.doubleClicked.connect(self.open_result)
        self.queue.log_line.connect(self.log.append)
        self.queue.experiment_changed.connect(self._refresh_status)

        self.populate_configs(self.project_root / "configs")
        self.statusBar().showMessage("ready")

    # --- config browsing ------------------------------------------------

    def populate_configs(self, folder: Path) -> None:
        self.config_list.clear()
        self.config_folder = Path(folder)
        if self.config_folder.is_dir():
            for p in sorted(self.config_folder.glob("*.yaml")):
                self.config_list.addItem(p.name)

    def pick_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Config folder",
                                                  str(self.project_root))
        if folder:
            self.populate_configs(Path(folder))

    def load_config(self, name: str) -> None:
        if not name:
            return
        try:
            self.form.load(self.config_folder / name)
            self.statusBar().showMessage(f"loaded {name}")
        except Exception as exc:  # noqa: BLE001 - surface to the user
            QMessageBox.warning(self, "Config error", str(exc))

    def _current_config(self) -> Path | None:
        item = self.config_list.currentItem()
        return self.config_folder / item.text() if item else None

    # --- actions -------------------------------------------------------

    def _new_out_dir(self, tag: str) -> Path:
        return self.results_root / f"{time.strftime('%H%M%S')}_{tag}"

    def run_current(self) -> None:
        base = self._current_config()
        if base is None:
            QMessageBox.information(self, "Run", "select a config first")
            return
        tag = base.stem
        out = self._new_out_dir(tag)
        try:
            out.mkdir(parents=True, exist_ok=True)
            self.form.save(out / "config.yaml")  # form state, validated
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid parameters", str(exc))
            return
        exp = self.queue.make_experiment(tag, out / "config.yaml", out)
        self.queue.enqueue(exp)
        self.tabs.setCurrentWidget(self.table)

    def run_sweep(self) -> None:
        base = self._current_config()
        if base is None:
            QMessageBox.information(self, "Sweep", "select a config first")
            return
        dlg = SweepDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        try:
            specs = [parse_param_spec(line.strip())
                     for line in dlg.specs.toPlainText().splitlines()
                     if line.strip()]
            if not specs:
                raise ValueError("no parameter specs given")
            params = dict(specs)
            if dlg.zip_box.isChecked():
                lengths = {len(v) for v in params.values()}
                if len(lengths) > 1:
                    raise ValueError("zip requires equally long lists")
                points = [dict(zip(params, combo))
                          for combo in zip(*params.values())]
            else:
                import itertools
                points = [dict(zip(params, combo)) for combo in
                          itertools.product(*params.values())]
        except ValueError as exc:
            QMessageBox.warning(self, "Sweep error", str(exc))
            return
        self.queue.max_parallel = dlg.jobs.value()
        stamp = time.strftime("%H%M%S")
        for i, overrides in enumerate(points):
            tag = "_".join(f"{k.split('.')[-1]}{v}"
                           for k, v in overrides.items())
            out = self.results_root / f"{stamp}_{base.stem}" / f"p{i:03d}_{tag}"
            exp = self.queue.make_experiment(f"{base.stem}:{tag}", base, out,
                                             overrides)
            self.queue.enqueue(exp)
        self.tabs.setCurrentWidget(self.table)

    def preview_structure(self) -> None:
        """SDE-style preview: mesh + doping export without solving, in a
        subprocess, then load into the 3D view."""
        base = self._current_config()
        if base is None:
            QMessageBox.information(self, "Structure",
                                    "select a config first")
            return
        out = self._new_out_dir(f"{base.stem}_structure")
        try:
            out.mkdir(parents=True, exist_ok=True)
            self.form.save(out / "config.yaml")
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid parameters", str(exc))
            return
        from PySide6.QtCore import QProcess

        from .run_queue import cli_command
        program, prefix = cli_command()
        proc = QProcess(self)
        proc.setProgram(program)
        proc.setArguments(prefix + ["structure", str(out / "config.yaml"),
                                    "-o", str(out)])
        proc.setProcessChannelMode(QProcess.MergedChannels)
        proc.readyReadStandardOutput.connect(
            lambda: [self.log.append(f"[structure] {ln}") for ln in
                     bytes(proc.readAllStandardOutput()).decode(
                         errors="replace").splitlines()])
        proc.finished.connect(
            lambda code, _s: self._structure_ready(out, code))
        self.statusBar().showMessage("building structure preview...")
        proc.start()

    def _structure_ready(self, out: Path, exit_code: int) -> None:
        if exit_code != 0:
            self.statusBar().showMessage("structure preview failed")
            return
        self.structure.load_dir(out / "vtk")
        self.tabs.setCurrentWidget(self.structure)
        self.statusBar().showMessage("structure loaded")

    def open_result(self, index) -> None:
        exp = self.model.experiments[index.row()]
        self.results.load_dir(exp.out_dir)
        self.tabs.setCurrentWidget(self.results)
        if (exp.out_dir / "vtk").is_dir():
            self.structure.load_dir(exp.out_dir / "vtk")

    def show_help(self) -> None:
        self.help.show()
        self.help.raise_()
        self.help.activateWindow()

    def show_about(self) -> None:
        AboutDialog(self).exec()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        self.help.close()  # the guide window follows the main window
        super().closeEvent(event)

    def _refresh_status(self) -> None:
        counts: dict = {}
        for e in self.model.experiments:
            counts[e.status] = counts.get(e.status, 0) + 1
        self.statusBar().showMessage(
            "  ".join(f"{k}: {v}" for k, v in sorted(counts.items()))
            or "ready")
