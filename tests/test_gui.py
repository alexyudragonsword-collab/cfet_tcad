"""GUI smoke tests (offscreen; skipped when PySide6 is not installed)."""

import json
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")


@pytest.fixture(scope="module")
def qapp():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


def test_fom_summary_variants():
    from cfet_tcad.gui.experiment_table import fom_summary

    idvg = {"Vd = +0.05 V": {"ss_mv_per_dec": 74.0, "ion_a": 1e-5,
                             "ioff_a": 1e-10, "vt_constant_current_v": 0.17,
                             "vdd_v": 0.05},
            "Vd = +0.70 V": {"ss_mv_per_dec": 73.9, "ion_a": 3e-5,
                             "ioff_a": 3e-10, "vt_constant_current_v": 0.11,
                             "vdd_v": 0.7},
            "dibl_mv_per_v": 90.0}
    s = fom_summary(idvg)
    assert s["SS [mV/dec]"] == 73.9        # saturation entry wins
    assert s["DIBL [mV/V]"] == 90.0

    cfet = {"nFET": {"ss_mv_per_dec": 76.7, "ion_a": 4e-5, "ioff_a": 5e-10,
                     "vt_constant_current_v": 0.10, "vdd_v": 0.7},
            "pFET": {"ss_mv_per_dec": 76.9, "ion_a": 3e-5, "ioff_a": 4e-10,
                     "vt_constant_current_v": -0.11, "vdd_v": -0.7}}
    assert fom_summary(cfet)["SS [mV/dec]"] == 76.7  # nFET shown

    vtc = {"vm_v": 0.34, "max_gain": 9.4, "voh_v": 0.7, "vol_v": 1e-6}
    assert fom_summary(vtc)["Vt [V]"] == 0.34
    assert fom_summary({}) == {}


def test_experiment_model_status_colors(qapp, tmp_path):
    from PySide6.QtCore import Qt

    from cfet_tcad.gui.experiment_table import (
        COLUMNS, Experiment, ExperimentModel, STATUS_COLORS)

    model = ExperimentModel()
    row = model.add(Experiment(name="t", config_path=tmp_path / "c.yaml",
                               out_dir=tmp_path, overrides={"a.b": 1}))
    assert model.rowCount() == 1
    status_col = COLUMNS.index("Status")
    idx = model.index(row, status_col)
    assert model.data(idx) == "pending"
    assert model.data(idx, Qt.BackgroundRole) == STATUS_COLORS["pending"]
    model.experiments[row].status = "done"
    assert model.data(idx, Qt.BackgroundRole) == STATUS_COLORS["done"]
    assert model.data(model.index(row, 1)) == "b=1"


def test_config_form_roundtrip(qapp):
    from cfet_tcad.gui.config_form import ConfigForm

    form = ConfigForm()
    form.load("configs/nsheet_nfet_2d.yaml")
    raw = form.to_raw()  # validates through build_config
    assert raw["device"]["l_gate_nm"] == 15.0
    assert raw["simulation"]["vd"] == [0.05, 0.7]
    # edit a field and confirm it lands (and still validates)
    form._widgets[("device", "l_gate_nm")].setText("21.0")
    assert form.to_raw()["device"]["l_gate_nm"] == 21.0
    # invalid values surface as ValueError from the dataclass validation
    form._widgets[("device", "polarity")].setCurrentText("x")
    with pytest.raises(ValueError):
        form.to_raw()


def test_progress_line_parsing():
    from cfet_tcad.gui.run_queue import parse_progress_line

    assert parse_progress_line("@@PROGRESS 3/29") == (3, 29)
    assert parse_progress_line("@@PROGRESS 0/15") == (0, 15)
    assert parse_progress_line("Iteration: 3") is None
    assert parse_progress_line("x @@PROGRESS 3/29") is None


def test_status_cell_shows_running_percent(qapp, tmp_path):
    from PySide6.QtCore import Qt

    from cfet_tcad.gui.experiment_table import (
        COLUMNS, Experiment, ExperimentModel, STATUS_COLORS)

    model = ExperimentModel()
    exp = Experiment(name="t", config_path=tmp_path / "c.yaml",
                     out_dir=tmp_path)
    row = model.add(exp)
    idx = model.index(row, COLUMNS.index("Status"))
    exp.status = "running"
    exp.progress = 0.45
    assert model.data(idx) == "running 45%"
    assert "stopped" in STATUS_COLORS  # new terminal state has a color
    exp.status = "stopped"
    assert model.data(idx) == "stopped"
    assert model.data(idx, Qt.BackgroundRole) == STATUS_COLORS["stopped"]


def test_model_remove_and_identity(qapp, tmp_path):
    from cfet_tcad.gui.experiment_table import Experiment, ExperimentModel

    model = ExperimentModel()
    exps = [Experiment(name=f"e{i}", config_path=tmp_path / "c.yaml",
                       out_dir=tmp_path) for i in range(3)]
    for e in exps:
        model.add(e)
    # identical field values must still be distinct dict keys (identity
    # semantics) - two runs of the same config must not collide
    twin = Experiment(name="e0", config_path=tmp_path / "c.yaml",
                      out_dir=tmp_path)
    assert {exps[0]: 1, twin: 2}[exps[0]] == 1

    model.remove(1)  # drop the middle row
    assert [e.name for e in model.experiments] == ["e0", "e2"]
    assert model.rowCount() == 2
    assert model.row_of(exps[2]) == 1  # rows shifted, lookup stays right


def test_stop_queued_experiment(qapp, tmp_path):
    from cfet_tcad.gui.experiment_table import Experiment, ExperimentModel
    from cfet_tcad.gui.run_queue import RunQueue

    model = ExperimentModel()
    queue = RunQueue(model, max_parallel=0)  # nothing ever starts
    exp = Experiment(name="q", config_path=tmp_path / "c.yaml",
                     out_dir=tmp_path)
    queue.add(exp)
    queue.start(exp)
    assert exp.status == "queued"
    queue.stop(exp)
    assert exp.status == "stopped"
    queue.max_parallel = 2
    queue._maybe_start()  # scheduler must not resurrect a stopped row
    assert exp.status == "stopped" and not queue._procs
    queue.stop(exp)  # idempotent on terminal states
    assert exp.status == "stopped"


def test_pending_lifecycle_and_run_all(qapp, tmp_path):
    from cfet_tcad.gui.experiment_table import Experiment, ExperimentModel
    from cfet_tcad.gui.run_queue import RunQueue

    model = ExperimentModel()
    queue = RunQueue(model, max_parallel=0)  # scheduler can never launch
    exps = [Experiment(name=f"e{i}", config_path=tmp_path / "c.yaml",
                       out_dir=tmp_path) for i in range(4)]
    for e in exps:
        queue.add(e)
    # added rows are pending and the scheduler leaves them alone
    queue._maybe_start()
    assert all(e.status == "pending" for e in exps)

    # per-row start queues exactly that one
    queue.start(exps[0])
    assert exps[0].status == "queued"
    assert [e.status for e in exps[1:]] == ["pending"] * 3

    # run_all picks up pending/stopped/failed but not done
    exps[1].status = "done"
    exps[2].status = "failed"
    queue.run_all()
    assert exps[1].status == "done"      # finished rows stay finished
    assert exps[2].status == "queued"    # failed rows retry
    assert exps[3].status == "queued"

    # in-place rerun: a finished row requeues with progress/fom cleared
    exps[1].fom = {"Ion [A]": 1e-5}
    exps[1].progress = 1.0
    queue.start(exps[1])
    assert exps[1].status == "queued"
    assert exps[1].fom == {} and exps[1].progress is None
    # starting an already queued row is a no-op
    queue.start(exps[1])
    assert exps[1].status == "queued"


def test_run_queue_materializes_point_config(qapp, tmp_path):
    from cfet_tcad.gui.experiment_table import ExperimentModel
    from cfet_tcad.gui.run_queue import RunQueue

    queue = RunQueue(ExperimentModel())
    exp = queue.make_experiment("pt", "configs/nsheet_nfet_2d.yaml",
                                tmp_path / "p0",
                                overrides={"device.l_gate_nm": 18.0})
    assert exp.config_path.exists()
    import yaml
    raw = yaml.safe_load(exp.config_path.read_text())
    assert raw["device"]["l_gate_nm"] == 18.0
    assert exp.status == "pending"  # nothing runs before its Run button


def test_main_window_constructs(qapp, tmp_path):
    import cfet_tcad
    from PySide6.QtCore import Qt

    from cfet_tcad.gui.main_window import MainWindow

    win = MainWindow(project_root=tmp_path)  # empty project: no configs
    assert win.windowTitle() == (
        f"{cfet_tcad.__app_name__} v{cfet_tcad.__version__}")
    assert win.config_list.count() == 0
    # the folder path is surfaced above the YAML list
    assert win.folder_label.text() == str(tmp_path / "configs")
    # single composite workspace: Experiments on top, Results bottom-left,
    # Structure 3D bottom-right (the guide is a window, not a tab)
    assert win.center_split.orientation() == Qt.Vertical
    assert win.center_split.count() == 2
    assert win.center_split.widget(0) is win.table
    assert win.bottom_split.orientation() == Qt.Horizontal
    assert win.bottom_split.widget(0) is win.results
    assert win.bottom_split.widget(1) is win.structure
    # toolbar drives the whole queue; per-row buttons drive one row
    assert [a.text() for a in win.toolbar.actions()] == ["Run All",
                                                         "Stop All"]
    # menu bar: Open (config folder) sits left of Help
    menus = [a.text() for a in win.menuBar().actions()]
    assert menus == ["Open", "&Help"]
    actions = [a.text() for a in win.menuBar().actions()[1].menu().actions()]
    assert actions == ["User Guide / 用户指南",
                       "Manual (中英双语) / 说明书",
                       f"About {cfet_tcad.__app_name__}"]
    win.show_help()
    assert win.help.isVisible() and win.help.isWindow()
    win.show_manual()
    assert win.manual.isVisible() and win.manual.isWindow()
    win.close()
    assert not win.help.isVisible()      # both follow the main window
    assert not win.manual.isVisible()


def test_row_action_buttons_follow_rows(qapp, tmp_path):
    from cfet_tcad.gui.experiment_table import COLUMNS
    from cfet_tcad.gui.main_window import MainWindow

    win = MainWindow(project_root=tmp_path)
    (win.config_folder).mkdir(parents=True, exist_ok=True)
    cfg = win.config_folder / "a.yaml"
    import shutil
    shutil.copyfile("configs/nsheet_nfet_2d.yaml", cfg)
    exp = win.add_config_to_experiments(cfg)
    assert exp.status == "pending"
    assert len(win._action_widgets) == 1
    w = win._action_widgets[0]
    assert w.exp is exp
    # pending: Run enabled, Stop disabled
    assert w.run_btn.isEnabled() and not w.stop_btn.isEnabled()
    exp.status = "running"
    win._refresh_action_row(0)
    assert not w.run_btn.isEnabled() and w.stop_btn.isEnabled()
    # the Actions column renders through widgets, not model text
    col = COLUMNS.index("Actions")
    assert win.model.data(win.model.index(0, col)) is None
    # removing the row rebuilds the strips
    win.model.remove(0)
    assert win._action_widgets == []
    win.close()


def test_config_file_operations(qapp, tmp_path):
    from cfet_tcad.gui.main_window import MainWindow

    win = MainWindow(project_root=tmp_path)
    win.config_folder.mkdir(parents=True, exist_ok=True)
    import shutil
    src = win.config_folder / "base.yaml"
    shutil.copyfile("configs/nsheet_nfet_2d.yaml", src)
    win.populate_configs()
    assert win.config_list.count() == 1

    copy = win.copy_config(src, "variant")  # extension added automatically
    assert copy.name == "variant.yaml" and copy.exists()
    assert win.config_list.count() == 2
    with pytest.raises(FileExistsError):
        win.copy_config(src, "variant.yaml")

    win.delete_config(copy)
    assert not copy.exists()
    assert win.config_list.count() == 1
    win.close()


def test_step_files_listed_and_dialog_template(qapp, tmp_path):
    gmsh = pytest.importorskip("gmsh")

    from cfet_tcad.gui.main_window import MainWindow
    from cfet_tcad.gui.step_dialog import StepConvertDialog

    win = MainWindow(project_root=tmp_path)
    win.config_folder.mkdir(parents=True, exist_ok=True)
    step = win.config_folder / "cad.step"
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("t")
        gmsh.model.occ.addBox(0, 0, 0, 10, 5, 3)
        gmsh.model.occ.synchronize()
        gmsh.write(str(step))
    finally:
        gmsh.finalize()
    win.populate_configs()
    assert [win.config_list.item(i).text()
            for i in range(win.config_list.count())] == ["cad.step"]

    dlg = StepConvertDialog(step)
    text = dlg.editor.toPlainText()
    # the discovered volume table and the spec skeleton are prefilled
    assert "step_file: cad.step" in text
    assert "unit_cm" in text and "tag" in text
    assert dlg.spec_path.name == "cad_import.yaml"
    fired: list = []
    dlg.convert_requested.connect(fired.append)
    dlg._convert()
    assert dlg.spec_path.exists() and fired == [dlg.spec_path]
    win.close()


def test_params_dialog_save_and_save_as(qapp, tmp_path, monkeypatch):
    from cfet_tcad.gui.params_dialog import ParamsDialog

    import shutil
    path = tmp_path / "dev.yaml"
    shutil.copyfile("configs/nsheet_nfet_2d.yaml", path)
    saved: list = []
    dlg = ParamsDialog(path)
    dlg.saved.connect(saved.append)
    # edit a field, Save overwrites the opened file
    dlg.form._widgets[("device", "l_gate_nm")].setText("21.0")
    dlg.save()
    import yaml
    assert yaml.safe_load(path.read_text())["device"]["l_gate_nm"] == 21.0
    assert saved == [path]

    # Save As writes a second file (file dialog stubbed out)
    target = tmp_path / "dev_b.yaml"
    monkeypatch.setattr(
        "cfet_tcad.gui.params_dialog.QFileDialog.getSaveFileName",
        lambda *a, **k: (str(target), "YAML (*.yaml)"))
    dlg2 = ParamsDialog(path)
    dlg2.saved.connect(saved.append)
    dlg2.save_as()
    assert target.exists() and saved[-1] == target
    assert yaml.safe_load(target.read_text())["device"]["l_gate_nm"] == 21.0
    # invalid values never reach disk
    dlg3 = ParamsDialog(path)
    dlg3.form._widgets[("device", "polarity")].setCurrentText("x")
    before = path.read_text()
    monkeypatch.setattr(
        "cfet_tcad.gui.params_dialog.QMessageBox.warning",
        lambda *a, **k: None)
    dlg3.save()
    assert path.read_text() == before


def test_elided_labels_do_not_pin_pane_widths(qapp, tmp_path):
    from cfet_tcad.gui.widgets import ElidedLabel

    # do NOT clear CFET_TCAD_NO_3D here: the packaging CI sets it to keep
    # StructureView from spawning a real VTK interactor, which
    # access-violates on the headless Windows runner.  The 3D-title
    # assertions below are already guarded by `plotter is not None`.
    from cfet_tcad.gui.main_window import MainWindow

    deep = tmp_path.joinpath(*(["very_long_directory_name"] * 6))
    (deep / "configs").mkdir(parents=True)
    win = MainWindow(project_root=deep)
    # the folder label shows the (long) path but never demands its width
    assert isinstance(win.folder_label, ElidedLabel)
    assert str(deep) in win.folder_label.text()
    assert win.folder_label.minimumSizeHint().width() < 80
    assert win.folder_label.toolTip() == win.folder_label.text()
    # Structure 3D's title label has the same guarantee
    if win.structure.plotter is not None:
        assert isinstance(win.structure.title, ElidedLabel)
        win.structure.title.setText(str(deep / "results" / "vtk"))
        assert win.structure.title.minimumSizeHint().width() < 80
    win.close()


def test_layout_adapts_to_window_size(qapp, tmp_path):
    from cfet_tcad.gui.main_window import MainWindow

    win = MainWindow(project_root=tmp_path)
    # window sized from the screen, never past its available area
    avail = win.screen().availableGeometry()
    assert win.width() <= avail.width() and win.height() <= avail.height()
    win.resize(1600, 1000)  # pretend a large display
    win.show()
    qapp.processEvents()
    # first show distributes proportionally: experiments ~1/3 of the
    # center, config browser a modest fraction of the width
    top, bottom = win.center_split.sizes()
    assert 0.2 < top / (top + bottom) < 0.45
    left, right = win.hsplit.sizes()
    assert left / (left + right) <= 0.25
    # the left pane can be dragged much narrower than any path text
    win.hsplit.setSizes([60, left + right - 60])
    assert win.hsplit.sizes()[0] < 120
    win.close()


def test_structure_view_respects_no3d_gate(qapp, monkeypatch):
    from cfet_tcad.gui.structure_view import NO_3D_ENV, StructureView

    monkeypatch.setenv(NO_3D_ENV, "1")
    view = StructureView()
    assert view.plotter is None  # degraded to a label, no VTK interactor


def test_about_dialog_and_version(qapp):
    import cfet_tcad
    from cfet_tcad.gui.about_dialog import ABOUT_HTML, AboutDialog

    assert cfet_tcad.__version__ == "0.5"
    assert cfet_tcad.__author__ == "Yu Rui"
    assert "Yu Rui" in ABOUT_HTML and "0.5" in ABOUT_HTML
    # copyright is surfaced in About and available as package metadata
    assert cfet_tcad.__copyright__ == "Copyright © 2026 Yu Rui"
    assert cfet_tcad.__copyright__ in ABOUT_HTML
    assert "2026" in ABOUT_HTML and "Apache" in ABOUT_HTML
    dlg = AboutDialog()
    assert dlg.windowTitle() == f"About {cfet_tcad.__app_name__}"
    dlg.close()

    # pyproject stays in sync with the package version
    import re
    from pathlib import Path
    text = Path("pyproject.toml").read_text()
    assert re.search(r'^version = "0\.5"$', text, re.M)
    # the license we advertise actually ships
    assert Path("LICENSE").exists()
    assert "Apache License" in Path("LICENSE").read_text()


def test_manual_renders_with_language_toggle(qapp):
    from cfet_tcad.gui.help_view import MANUALS, HelpView, manual_path

    # both single-language manuals ship
    assert manual_path("English").exists()
    assert manual_path("中文").exists()

    view = HelpView(docs=MANUALS, title="Manual / 说明书")
    view.set_language("English")
    text = view.browser.toPlainText()
    for kw in ("Features", "Scope", "Benchmarking", "Limitations", "Ion"):
        assert kw in text
    assert "软件特性" not in text          # single-language, not both at once
    view.set_language("中文")
    text = view.browser.toPlainText()
    for kw in ("软件特性", "适用范围", "对标", "局限"):
        assert kw in text
    assert "Limitations" not in text


def test_default_project_root(tmp_path, monkeypatch):
    from cfet_tcad.gui.app import default_project_root

    exe_dir = tmp_path / "install"
    (exe_dir / "configs").mkdir(parents=True)
    cwd = tmp_path / "somewhere"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    # explicit argument always wins
    assert default_project_root(["x", "/proj"], True, exe_dir) \
        == __import__("pathlib").Path("/proj")
    # frozen + no configs in cwd -> the install dir (shipped examples)
    assert default_project_root(["x"], True, exe_dir) == exe_dir
    # dev runs keep the working directory
    assert default_project_root(["x"], False, exe_dir) == cwd
    # a cwd that has its own configs/ wins even when frozen
    (cwd / "configs").mkdir()
    assert default_project_root(["x"], True, exe_dir) == cwd


def test_sweep_dialog_imports_points_csv(qapp, tmp_path):
    from cfet_tcad.gui.main_window import SweepDialog

    doe = tmp_path / "doe.csv"
    doe.write_text("device.l_gate_nm,fom.ss\n12,74\n15,71\n",
                   encoding="utf-8")
    dlg = SweepDialog()
    dlg.load_points_csv(doe)
    # rows become paired tuples: spec lines + zip mode (fom column drops)
    assert dlg.specs.toPlainText() == "device.l_gate_nm=12,15"
    assert dlg.zip_box.isChecked()
    dlg.close()


def test_app_icon_ships(qapp):
    from pathlib import Path

    from cfet_tcad.gui.icon import app_icon, icon_path

    assert icon_path().exists()
    assert not app_icon().isNull()
    # the exe-resource icon used by both Windows packaging lanes
    assert Path("packaging/app.ico").exists()


def test_help_guide_renders_with_images(qapp):
    import re

    from cfet_tcad.gui.help_view import GUIDES, HelpView, guide_path

    for language in GUIDES:
        path = guide_path(language)
        assert path.exists(), language
        # every referenced image must ship with the package
        text = path.read_text(encoding="utf-8")
        for img in re.findall(r'src="(img/[^"]+)"', text):
            assert (path.parent / img).exists(), img

    view = HelpView()
    view.set_language("English")
    text = view.browser.toPlainText()
    assert "User Guide" in text and "Physics models" in text
    view.set_language("中文")
    text = view.browser.toPlainText()
    assert "用户指南" in text and "物理模型" in text


def test_results_view_loads_fom(qapp, tmp_path):
    from cfet_tcad.gui.results_view import ResultsView

    (tmp_path / "fom.json").write_text(json.dumps(
        {"Vd = +0.70 V": {"ss_mv_per_dec": 74.0}}))
    (tmp_path / "idvg.csv").write_text(
        "vg_v,vd_v,id_a,is_a\n0.0,0.7,1e-10,-1e-10\n0.7,0.7,3e-5,-3e-5\n")
    view = ResultsView()
    view.load_dir(tmp_path)
    assert view.fom_table.rowCount() == 1
    assert "74" in view.fom_table.item(0, 1).text()
