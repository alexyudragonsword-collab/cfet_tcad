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
    assert model.data(idx) == "queued"
    assert model.data(idx, Qt.BackgroundRole) == STATUS_COLORS["queued"]
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
    assert exp.status == "queued"


def test_main_window_constructs(qapp, tmp_path):
    import cfet_tcad
    from cfet_tcad.gui.main_window import MainWindow

    win = MainWindow(project_root=tmp_path)  # empty project: no configs
    assert win.windowTitle() == (
        f"{cfet_tcad.__app_name__} v{cfet_tcad.__version__}")
    assert win.config_list.count() == 0
    # Experiments/Parameters/Results/Structure (the guide is a window,
    # not a tab)
    assert win.tabs.count() == 4
    # single Help entry point: the top-left menu opens the guide window
    menus = [a.text() for a in win.menuBar().actions()]
    assert menus == ["&Help"]
    actions = [a.text() for a in win.menuBar().actions()[0].menu().actions()]
    assert actions == ["User Guide / 用户指南",
                       f"About {cfet_tcad.__app_name__}"]
    win.show_help()
    assert win.help.isVisible() and win.help.isWindow()
    win.close()
    assert not win.help.isVisible()  # follows the main window


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
    dlg = AboutDialog()
    assert dlg.windowTitle() == f"About {cfet_tcad.__app_name__}"
    dlg.close()

    # pyproject stays in sync with the package version
    import re
    from pathlib import Path
    text = Path("pyproject.toml").read_text()
    assert re.search(r'^version = "0\.5"$', text, re.M)


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
