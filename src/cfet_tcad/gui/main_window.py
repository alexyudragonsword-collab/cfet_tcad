"""Main window: Sentaurus Workbench-style layout.

Left: config browser (current folder path on top; double-click a YAML to
edit it, right-click for Edit/Add/Copy/Delete).  Center: one composite
workspace - Experiments table on top (each row carries its own
Run/Stop/Sweep/Structure buttons), Results bottom-left, Structure 3D
bottom-right, all separated by draggable splitters.  Bottom: log console.
Toolbar holds the whole-queue Run All / Stop All; the menu bar has Open
(pick a config folder) and Help.
"""

import shutil
import time
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QListWidget,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableView,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

import cfet_tcad

from ..workflow.sweep import parse_param_spec
from .about_dialog import AboutDialog
from .experiment_table import COLUMNS, Experiment, ExperimentModel
from .help_view import MANUALS, HelpView
from .icon import app_icon
from .log_console import LogConsole
from .params_dialog import ParamsDialog
from .results_view import ResultsView
from .run_queue import RunQueue
from .structure_view import StructureView
from .widgets import ElidedLabel


class SweepDialog(QDialog):
    """Parameter specs, one per line: path=v1,v2,... (SWB experiment grid).
    A DOE table can also be imported from CSV (rows = design points)."""

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
        import_btn = QPushButton("Import CSV...")
        import_btn.setToolTip(
            "design-point table: dotted config paths as headers, one row "
            "per run (an edited sweep_summary.csv works)")
        import_btn.clicked.connect(self._import_csv)
        form = QFormLayout(self)
        form.addRow("parameters", self.specs)
        form.addRow("", self.zip_box)
        form.addRow("", import_btn)
        form.addRow("max parallel", self.jobs)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok
                                   | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _import_csv(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Import design points", "", "CSV (*.csv);;All files (*)")
        if path:
            try:
                self.load_points_csv(Path(path))
            except (ValueError, OSError) as exc:
                QMessageBox.warning(self, "Import failed", str(exc))

    def load_points_csv(self, path: Path) -> None:
        """Fill the dialog from a design-point CSV: rows become paired
        tuples, i.e. spec lines in zip mode."""
        from ..workflow.sweep import load_points_csv, points_to_zip_specs

        self.specs.setPlainText(
            "\n".join(points_to_zip_specs(load_points_csv(path))))
        self.zip_box.setChecked(True)


class RowActions(QWidget):
    """The per-row Run/Stop/Sweep/Structure button strip: every
    experiment row drives itself, independent of the toolbar."""

    def __init__(self, exp: Experiment, window: "MainWindow", parent=None):
        super().__init__(parent)
        self.exp = exp
        lay = QHBoxLayout(self)
        lay.setContentsMargins(2, 0, 2, 0)
        lay.setSpacing(2)

        def _btn(text: str, slot) -> QToolButton:
            b = QToolButton()
            b.setText(text)
            b.setAutoRaise(True)
            b.clicked.connect(slot)
            lay.addWidget(b)
            return b

        self.run_btn = _btn("Run", lambda: window.queue.start(exp))
        self.stop_btn = _btn("Stop", lambda: window.queue.stop(exp))
        self.sweep_btn = _btn("Sweep", lambda: window.run_sweep(exp))
        self.structure_btn = _btn("Structure",
                                  lambda: window.preview_structure(exp))
        self.refresh()

    def refresh(self) -> None:
        self.run_btn.setEnabled(
            self.exp.status in ("pending", "done", "failed", "stopped"))
        self.stop_btn.setEnabled(self.exp.status in ("queued", "running"))


class MainWindow(QMainWindow):
    def __init__(self, project_root: Path | None = None):
        super().__init__()
        self.setWindowTitle(
            f"{cfet_tcad.__app_name__} v{cfet_tcad.__version__}")
        self.setWindowIcon(app_icon())
        # size to the actual display instead of a fixed 1280x800: ~85%
        # of the available area, centered (fallback for headless tests)
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            avail = screen.availableGeometry()
            self.resize(int(avail.width() * 0.85),
                        int(avail.height() * 0.85))
            self.move(avail.center() - self.rect().center())
        else:  # pragma: no cover - no-screen environments
            self.resize(1280, 800)
        self._layout_initialized = False
        self.project_root = Path(project_root or Path.cwd())
        self.results_root = self.project_root / "results" / "gui"

        # widgets
        self.folder_label = ElidedLabel()
        self.folder_label.setStyleSheet("padding: 2px; color: #444;")
        self.config_list = QListWidget()
        self.model = ExperimentModel(self)
        self.queue = RunQueue(self.model, parent=self)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setDefaultSectionSize(28)
        self.results = ResultsView()
        self.log = LogConsole()
        self._action_widgets: list[RowActions] = []

        self.structure = StructureView()
        # the user guide lives in its own window, reached from the Help
        # menu (top-left) — not duplicated as a center tab
        self.help = HelpView()
        self.help.setWindowIcon(app_icon())
        self.help.setWindowTitle("User Guide / 用户指南")
        self.help.resize(920, 720)
        # the bilingual software manual (features / scope / benchmarking
        # / limitations): its own window, same language toggle
        self.manual = HelpView(docs=MANUALS, title="Manual / 说明书")
        self.manual.setWindowIcon(app_icon())
        self.manual.setWindowTitle("Manual / 说明书")
        self.manual.resize(920, 720)

        # left panel: current folder path above the YAML list
        left = QWidget()
        lbox = QVBoxLayout(left)
        lbox.setContentsMargins(0, 0, 0, 0)
        lbox.setSpacing(2)
        lbox.addWidget(self.folder_label)
        lbox.addWidget(self.config_list)

        # center workspace: Experiments over (Results | Structure 3D),
        # every pane resizable through the splitters
        self.bottom_split = QSplitter(Qt.Horizontal)
        self.bottom_split.addWidget(self.results)
        self.bottom_split.addWidget(self.structure)
        self.center_split = QSplitter(Qt.Vertical)
        self.center_split.addWidget(self.table)
        self.center_split.addWidget(self.bottom_split)
        self.center_split.setStretchFactor(0, 1)  # experiments: ~1/3
        self.center_split.setStretchFactor(1, 2)

        self.hsplit = QSplitter(Qt.Horizontal)
        self.hsplit.addWidget(left)
        self.hsplit.addWidget(self.center_split)
        self.hsplit.setStretchFactor(0, 1)
        self.hsplit.setStretchFactor(1, 4)
        self.vsplit = QSplitter(Qt.Vertical)
        self.vsplit.addWidget(self.hsplit)
        self.vsplit.addWidget(self.log)
        self.vsplit.setStretchFactor(0, 4)
        self.vsplit.setStretchFactor(1, 1)
        self.setCentralWidget(self.vsplit)

        # toolbar: whole-queue controls (per-row buttons drive one row)
        self.toolbar = QToolBar("main")
        self.toolbar.setMovable(False)
        self.addToolBar(self.toolbar)
        self.toolbar.addAction("Run All", self.queue.run_all)
        self.toolbar.addAction("Stop All", self.queue.stop_all)

        # menu bar: Open (config folder) left of Help.  Construct the
        # QMenu with an explicit parent instead of addMenu(str):
        # shiboken deletes the C++ menu of the string overload once the
        # temporary wrapper from menuBar().actions() is garbage collected
        open_act = QAction("Open", self)
        open_act.triggered.connect(self.pick_folder)
        self.menuBar().addAction(open_act)
        self.help_menu = QMenu("&Help", self)
        self.help_menu.addAction("User Guide / 用户指南", self.show_help)
        self.help_menu.addAction("Manual (中英双语) / 说明书",
                                 self.show_manual)
        self.help_menu.addAction(f"About {cfet_tcad.__app_name__}",
                                 self.show_about)
        self.menuBar().addMenu(self.help_menu)

        # wiring
        self.config_list.itemDoubleClicked.connect(
            lambda item: self.edit_config(self.config_folder / item.text()))
        self.config_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.config_list.customContextMenuRequested.connect(self.config_menu)
        self.table.doubleClicked.connect(self.open_result)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.table_menu)
        self.model.rowsInserted.connect(self._rebuild_action_widgets)
        self.model.rowsRemoved.connect(self._rebuild_action_widgets)
        self.model.modelReset.connect(self._rebuild_action_widgets)
        self.queue.log_line.connect(self.log.append)
        self.queue.experiment_changed.connect(self._refresh_status)
        self.queue.experiment_changed.connect(self._refresh_action_row)

        self.populate_configs(self.project_root / "configs")
        self.statusBar().showMessage("ready")

    def showEvent(self, event) -> None:  # noqa: N802 - Qt override
        """First show: distribute the splitters proportionally to the
        real window size.  Size hints are resolution-blind (a long path
        or a plot's minimum would dictate the layout); fixed pixels
        would only fit the display they were tuned on.  Later resizes
        and user drags are governed by the stretch factors as usual."""
        super().showEvent(event)
        if self._layout_initialized:
            return
        self._layout_initialized = True
        w, h = self.vsplit.width(), self.vsplit.height()
        self.vsplit.setSizes([int(h * 0.78), h - int(h * 0.78)])
        self.hsplit.setSizes([int(w * 0.16), w - int(w * 0.16)])
        ch = self.center_split.height()
        self.center_split.setSizes([ch // 3, ch - ch // 3])
        bw = self.bottom_split.width()
        self.bottom_split.setSizes([bw // 2, bw - bw // 2])

    # --- config browsing ------------------------------------------------

    def populate_configs(self, folder: Path | None = None) -> None:
        self.config_list.clear()
        self.config_folder = Path(folder or self.config_folder)
        self.folder_label.setText(str(self.config_folder))
        self.folder_label.setToolTip(str(self.config_folder))
        if self.config_folder.is_dir():
            names = [p.name for pattern in ("*.yaml", "*.step", "*.stp")
                     for p in self.config_folder.glob(pattern)]
            for name in sorted(names):
                self.config_list.addItem(name)

    def pick_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Config folder",
                                                  str(self.project_root))
        if folder:
            self.populate_configs(Path(folder))

    def config_menu(self, pos) -> None:
        """Right-click on a YAML: edit / add to experiments / copy /
        delete."""
        item = self.config_list.itemAt(pos)
        if item is None:
            return
        path = self.config_folder / item.text()
        menu = QMenu(self)
        if path.suffix.lower() in (".step", ".stp"):
            act_convert = menu.addAction("Convert to mesh...")
            act_volumes = menu.addAction("List volumes")
            chosen = menu.exec(self.config_list.viewport().mapToGlobal(pos))
            if chosen is act_convert:
                self.open_step_dialog(path)
            elif chosen is act_volumes:
                self.list_step_volumes(path)
            return
        act_edit = menu.addAction("Edit")
        act_add = menu.addAction("Add")
        act_copy = menu.addAction("Copy...")
        act_delete = menu.addAction("Delete")
        chosen = menu.exec(self.config_list.viewport().mapToGlobal(pos))
        if chosen is act_edit:
            self.edit_config(path)
        elif chosen is act_add:
            self.add_config_to_experiments(path)
        elif chosen is act_copy:
            self._copy_config_dialog(path)
        elif chosen is act_delete:
            self._delete_config_dialog(path)

    def edit_config(self, path: Path) -> None:
        """Pop up the parameter editor for one YAML (double-click or
        right-click -> Edit); .step files open the conversion dialog."""
        if path.suffix.lower() in (".step", ".stp"):
            self.open_step_dialog(path)
            return
        try:
            dlg = ParamsDialog(path, self)
        except Exception as exc:  # noqa: BLE001 - malformed YAML etc.
            QMessageBox.warning(self, "Config error", str(exc))
            return
        dlg.saved.connect(lambda _p: self.populate_configs())
        dlg.exec()

    def open_step_dialog(self, path: Path) -> None:
        """STEP conversion dialog: volume table + editable mapping spec."""
        from .step_dialog import StepConvertDialog
        try:
            dlg = StepConvertDialog(path, self)
        except Exception as exc:  # noqa: BLE001 - unreadable STEP etc.
            QMessageBox.warning(self, "STEP error", str(exc))
            return
        dlg.convert_requested.connect(self.convert_step_file)
        dlg.exec()

    def convert_step_file(self, spec_path: Path) -> None:
        """Run the CLI converter in a subprocess (a meshing crash must
        never take the GUI down); refresh the browser on success."""
        from PySide6.QtCore import QProcess

        from .run_queue import cli_command
        spec_path = Path(spec_path)
        out_msh = spec_path.with_name(
            spec_path.stem.removesuffix("_import") + ".msh")
        program, prefix = cli_command()
        proc = QProcess(self)
        proc.setProgram(program)
        proc.setArguments(prefix + ["import-step", str(spec_path),
                                    "-o", str(out_msh)])
        proc.setProcessChannelMode(QProcess.MergedChannels)
        self._step_log: list[str] = []
        proc.readyReadStandardOutput.connect(
            lambda: self._on_step_output(proc))
        proc.finished.connect(lambda code, _s: self._step_converted(code))
        self.statusBar().showMessage("converting STEP to mesh...")
        proc.start()

    def _on_step_output(self, proc) -> None:
        for ln in bytes(proc.readAllStandardOutput()).decode(
                errors="replace").splitlines():
            self._step_log.append(ln)
            self.log.append(f"[import-step] {ln}")

    def _step_converted(self, exit_code: int) -> None:
        if exit_code != 0:
            self.statusBar().showMessage("STEP conversion failed")
            # surface the error directly - the meaningful lines are the
            # ValueError/Traceback tail from the subprocess
            tail = "\n".join(self._step_log[-14:]) or "(no output captured)"
            QMessageBox.warning(
                self, "STEP conversion failed",
                "The mesh conversion failed. Most often a solid was left "
                "unmapped, or a contact bbox matched no face.\n\n"
                "Details (also in the Log panel):\n\n" + tail)
            return
        self.populate_configs()  # the starter YAML appears in the list
        self.statusBar().showMessage(
            "STEP converted - starter config added to the list")

    def list_step_volumes(self, path: Path) -> None:
        from ..geometry.step_import import _volume_table, discover_step
        try:
            table = _volume_table(discover_step(path))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "STEP error", str(exc))
            return
        for line in f"volumes in {path.name}:\n{table}".splitlines():
            self.log.append(line)

    def add_config_to_experiments(self, path: Path) -> Experiment:
        """Right-click -> Add: register the YAML as a *pending* experiment
        (nothing runs until its Run button / Run All)."""
        tag = path.stem
        exp = self.queue.make_experiment(tag, path, self._new_out_dir(tag))
        self.queue.add(exp)
        return exp

    def copy_config(self, path: Path, new_name: str) -> Path:
        """Copy a YAML inside the current folder under a new name."""
        if not new_name.endswith((".yaml", ".yml")):
            new_name += ".yaml"
        target = self.config_folder / new_name
        if target.exists():
            raise FileExistsError(f"{target.name} already exists")
        shutil.copyfile(path, target)
        self.populate_configs()
        return target

    def delete_config(self, path: Path) -> None:
        Path(path).unlink()
        self.populate_configs()

    def _copy_config_dialog(self, path: Path) -> None:
        name, ok = QInputDialog.getText(self, "Copy config", "Save copy as:",
                                        text=f"{path.stem}_copy.yaml")
        if not ok or not name.strip():
            return
        try:
            self.copy_config(path, name.strip())
        except (FileExistsError, OSError) as exc:
            QMessageBox.warning(self, "Copy failed", str(exc))

    def _delete_config_dialog(self, path: Path) -> None:
        answer = QMessageBox.question(
            self, "Delete config",
            f"Delete {path.name}?  The file is removed from disk.")
        if answer == QMessageBox.Yes:
            try:
                self.delete_config(path)
            except OSError as exc:
                QMessageBox.warning(self, "Delete failed", str(exc))

    # --- actions -------------------------------------------------------

    def _new_out_dir(self, tag: str) -> Path:
        return self.results_root / f"{time.strftime('%H%M%S')}_{tag}"

    def run_sweep(self, exp: Experiment) -> None:
        """Per-row Sweep: expand a parameter grid over this experiment's
        config.  Every point lands as pending - Run All starts them."""
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
        base_tag = exp.name.replace(":", "_")  # keep paths portable
        for i, overrides in enumerate(points):
            tag = "_".join(f"{k.split('.')[-1]}{v}"
                           for k, v in overrides.items())
            out = self.results_root / f"{stamp}_{base_tag}" / f"p{i:03d}_{tag}"
            child = self.queue.make_experiment(f"{exp.name}:{tag}",
                                               exp.config_path, out,
                                               overrides)
            self.queue.add(child)

    def preview_structure(self, exp: Experiment) -> None:
        """SDE-style preview: mesh + doping export without solving, in a
        subprocess, then load into the 3D view.  Output goes to a
        structure/ subdir so a later run's vtk/ stays untouched."""
        out = exp.out_dir / "structure"
        out.mkdir(parents=True, exist_ok=True)
        from PySide6.QtCore import QProcess

        from .run_queue import cli_command
        program, prefix = cli_command()
        proc = QProcess(self)
        proc.setProgram(program)
        proc.setArguments(prefix + ["structure", str(exp.config_path),
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
        self.statusBar().showMessage("structure loaded")

    # --- experiments table ----------------------------------------------

    def _rebuild_action_widgets(self, *_args) -> None:
        """(Re)install the per-row button strips.  Index widgets do not
        follow rows across inserts/removes, so rebuild them all - row
        counts are small."""
        col = COLUMNS.index("Actions")
        self._action_widgets = []
        for row, exp in enumerate(self.model.experiments):
            w = RowActions(exp, self)
            self.table.setIndexWidget(self.model.index(row, col), w)
            self._action_widgets.append(w)
        self.table.resizeColumnToContents(col)

    def _refresh_action_row(self, row: int) -> None:
        if 0 <= row < len(self._action_widgets):
            self._action_widgets[row].refresh()

    def table_menu(self, pos) -> None:
        """Right-click on an experiment row: stop / remove / open folder."""
        index = self.table.indexAt(pos)
        if not index.isValid():
            return
        row = index.row()
        exp = self.model.experiments[row]
        menu = QMenu(self)
        act_stop = menu.addAction("Stop")
        act_stop.setEnabled(exp.status in ("queued", "running"))
        act_remove = menu.addAction("Remove from list (keeps files)")
        act_remove.setEnabled(exp.status != "running")
        act_open = menu.addAction("Open results folder")
        chosen = menu.exec(self.table.viewport().mapToGlobal(pos))
        if chosen is act_stop:
            self.queue.stop(exp)
        elif chosen is act_remove:
            self.model.remove(row)
        elif chosen is act_open:
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices
            QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(exp.out_dir)))

    def open_result(self, index) -> None:
        exp = self.model.experiments[index.row()]
        self.results.load_dir(exp.out_dir)
        if (exp.out_dir / "vtk").is_dir():
            self.structure.load_dir(exp.out_dir / "vtk")

    def show_help(self) -> None:
        self.help.show()
        self.help.raise_()
        self.help.activateWindow()

    def show_manual(self) -> None:
        self.manual.show()
        self.manual.raise_()
        self.manual.activateWindow()

    def show_about(self) -> None:
        AboutDialog(self).exec()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        self.help.close()  # the guide/manual windows follow the main one
        self.manual.close()
        super().closeEvent(event)

    def _refresh_status(self) -> None:
        counts: dict = {}
        for e in self.model.experiments:
            counts[e.status] = counts.get(e.status, 0) + 1
        self.statusBar().showMessage(
            "  ".join(f"{k}: {v}" for k, v in sorted(counts.items()))
            or "ready")
