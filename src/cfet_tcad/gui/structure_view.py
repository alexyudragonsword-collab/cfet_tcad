"""Interactive 3D structure/field view (SDE + Sentaurus Visual 3D analog).

Embeds a pyvistaqt QtInteractor when the viz extra is installed; degrades
to an explanatory label otherwise so the GUI core has no hard dependency
on VTK.
"""

from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

try:
    import pyvista as pv
    from pyvistaqt import QtInteractor

    from ..io import render3d
    HAVE_PYVISTA = True
except ImportError:  # pragma: no cover - exercised only without the extra
    HAVE_PYVISTA = False


class StructureView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        if not HAVE_PYVISTA:
            layout.addWidget(QLabel(
                "3D view requires the viz extra:\n"
                "    pip install -e '.[viz]'   (pyvista + pyvistaqt)"))
            self.plotter = None
            return

        self.field_box = QComboBox()
        self.field_box.addItem("Structure")
        self.clip_box = QCheckBox("clip open")
        self.snap_box = QComboBox()  # bias-point snapshots
        self.title = QLabel("no structure loaded")
        bar = QHBoxLayout()
        bar.setContentsMargins(4, 4, 4, 0)
        bar.addWidget(self.title)
        bar.addStretch(1)
        bar.addWidget(QLabel("snapshot"))
        bar.addWidget(self.snap_box)
        bar.addWidget(QLabel("field"))
        bar.addWidget(self.field_box)
        bar.addWidget(self.clip_box)
        layout.addLayout(bar)

        self.plotter = QtInteractor(self)
        self.plotter.set_background("white")
        layout.addWidget(self.plotter, stretch=1)

        self._dir: Path | None = None
        self.field_box.currentTextChanged.connect(lambda _t: self._redraw())
        self.snap_box.currentTextChanged.connect(lambda _t: self._redraw())
        self.clip_box.toggled.connect(lambda _c: self._redraw())

    # --- data flow ----------------------------------------------------------

    def load_dir(self, vtk_dir: Path) -> None:
        if self.plotter is None:
            return
        vtk_dir = Path(vtk_dir)
        prefixes = render3d.snapshot_prefixes(vtk_dir)
        if not prefixes:
            self.title.setText(f"no VTK snapshots in {vtk_dir}")
            return
        self._dir = vtk_dir
        self.title.setText(str(vtk_dir))
        for box in (self.snap_box, self.field_box):
            box.blockSignals(True)
        self.snap_box.clear()
        self.snap_box.addItems(prefixes)
        self.snap_box.setCurrentIndex(len(prefixes) - 1)
        meshes = render3d.load_snapshot(vtk_dir, prefixes[-1])
        current = self.field_box.currentText()
        self.field_box.clear()
        choices = render3d.field_choices(meshes)
        self.field_box.addItems(choices)
        if current in choices:
            self.field_box.setCurrentText(current)
        for box in (self.snap_box, self.field_box):
            box.blockSignals(False)
        self._redraw()

    def _redraw(self) -> None:
        if self.plotter is None or self._dir is None:
            return
        prefix = self.snap_box.currentText() or None
        field = self.field_box.currentText() or None
        self.plotter.clear()
        try:
            meshes = render3d.load_snapshot(self._dir, prefix)
            render3d.add_device(
                self.plotter, meshes, field=field,
                clip="z" if self.clip_box.isChecked() else None)
            self.plotter.add_axes()
            self.plotter.reset_camera()
        except (FileNotFoundError, ValueError) as exc:
            self.title.setText(str(exc))
        self.plotter.render()
