"""STEP conversion dialog: discovery table + editable mapping spec.

Double-clicking a .step in the config browser (or right-click ->
Convert to mesh...) opens this dialog.  Discovery runs in-process (pure
gmsh, no GL); the actual conversion runs through the CLI in a QProcess,
like the structure preview, so a meshing crash never takes the GUI down.
"""

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPlainTextEdit,
    QVBoxLayout,
)

SPEC_TEMPLATE = """\
# Mapping spec for {step_name} - edit, then press Convert.
# Volumes found in the file (tag / CAD label / bbox in CAD units):
{volume_table}
#
# Selectors: label (regex on the CAD label), volume (tag or [tags]),
# bbox ([x0,y0,z0,x1,y1,z1], CAD units).  Every volume must be claimed
# by exactly one region.  Contacts use bbox only.

step_file: {step_name}
unit_cm: 1.0e-7        # 1 CAD unit in cm (nm: 1e-7, um: 1e-4, mm: 0.1)
mesh_size: 2.0         # characteristic length, CAD units

regions:
  bulk: {{select: {{volume: 1}}, material: Silicon}}
  gox:  {{select: {{volume: 2}}, material: Oxide}}

contacts:
  source: {{select: {{bbox: [0, 0, 0, 0, 1, 1]}}, region: bulk}}
  drain:  {{select: {{bbox: [1, 0, 0, 1, 1, 1]}}, region: bulk}}
  gate:   {{select: {{bbox: [0, 1, 0, 1, 1, 1]}}, region: gox}}

interfaces:
  si_ox: [bulk, gox]
"""


def spec_template(step_path: Path) -> str:
    """The prefilled dialog text: discovered volume table (as comments)
    plus a spec skeleton to edit."""
    from ..geometry.step_import import _volume_table, discover_step

    table = "\n".join(f"# {line}" for line in
                      _volume_table(discover_step(step_path)).splitlines())
    return SPEC_TEMPLATE.format(step_name=Path(step_path).name,
                                volume_table=table)


class StepConvertDialog(QDialog):
    #: emitted with the spec path once the user presses Convert; the
    #: main window owns the actual QProcess run
    convert_requested = Signal(Path)

    def __init__(self, step_path: Path, parent=None):
        super().__init__(parent)
        self.step_path = Path(step_path)
        self.setWindowTitle(f"Convert {self.step_path.name} to mesh")
        from .widgets import fit_to_screen
        fit_to_screen(self, 720, 640)

        self.editor = QPlainTextEdit()
        self.editor.setFont(QFont("monospace"))
        self.editor.setPlainText(spec_template(self.step_path))

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        self.convert_btn = buttons.addButton(
            "Convert", QDialogButtonBox.AcceptRole)
        buttons.accepted.connect(self._convert)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Map every volume to a region, place the contacts, set "
            "unit_cm - then Convert writes <name>.msh plus a starter "
            "config YAML next to the STEP file."))
        layout.addWidget(self.editor)
        layout.addWidget(buttons)

    @property
    def spec_path(self) -> Path:
        return self.step_path.with_name(f"{self.step_path.stem}_import.yaml")

    def _convert(self) -> None:
        self.spec_path.write_text(self.editor.toPlainText(),
                                  encoding="utf-8")
        self.convert_requested.emit(self.spec_path)
        self.accept()
