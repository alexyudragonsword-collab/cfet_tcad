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
    QMessageBox,
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
# by exactly one region.  One region per volume is scaffolded below and
# all start as Silicon - merge volumes into shared regions and set the
# gate-oxide ones to `material: Oxide` as needed.  Contacts use bbox only.

step_file: {step_name}
unit_cm: 1.0e-7        # 1 CAD unit in cm (nm: 1e-7, um: 1e-4, mm: 0.1)
mesh_size: 2.0         # characteristic length, CAD units

regions:
{regions}

# contacts:   # add bbox selectors once you know the S/D and gate faces
#   source: {{select: {{bbox: [x0, y0, z0, x1, y1, z1]}}, region: region_1}}
#   gate:   {{select: {{bbox: [x0, y0, z0, x1, y1, z1]}}, region: region_2}}

# interfaces:   # shared faces between two regions are found automatically
#   si_ox: [region_1, region_2]
"""


def spec_template(step_path: Path) -> str:
    """The text prefilled into the dialog editor.

    If a ready-made mapping spec ships next to the STEP file (the
    bundled demos do: ``<stem>_import.yaml``), use it verbatim so Convert
    works out of the box.  Otherwise scaffold a spec that claims *every*
    discovered volume with its own region - conversion then never fails
    on an unclaimed solid, and the user edits materials / merges regions
    / adds contacts from a working starting point."""
    step_path = Path(step_path)
    sibling = step_path.with_name(f"{step_path.stem}_import.yaml")
    if sibling.exists():
        return sibling.read_text(encoding="utf-8")

    from ..geometry.step_import import _volume_table, discover_step

    volumes = discover_step(step_path)
    table = "\n".join(f"# {line}" for line in
                      _volume_table(volumes).splitlines())
    regions = "\n".join(
        f"  region_{v.tag}: {{select: {{volume: {v.tag}}}, "
        f"material: Silicon}}" for v in volumes)
    return SPEC_TEMPLATE.format(step_name=step_path.name,
                                volume_table=table, regions=regions)


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
        try:
            self.spec_path.write_text(self.editor.toPlainText(),
                                      encoding="utf-8")
        except OSError as exc:
            QMessageBox.warning(
                self, "Cannot write spec",
                f"Could not write {self.spec_path.name}:\n{exc}\n\n"
                "The install folder may be read-only (e.g. Program "
                "Files). Copy the app somewhere writable, or use Open to "
                "point at a writable config folder.")
            return
        self.convert_requested.emit(self.spec_path)
        self.accept()
