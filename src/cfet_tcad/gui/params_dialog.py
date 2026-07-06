"""Pop-up parameter editor for one YAML config file.

Replaces the old always-on Parameters tab: double-clicking (or
right-click -> Edit on) a config in the browser opens this dialog.  The
embedded ConfigForm validates through build_config on save, so nothing
invalid reaches disk.  Save overwrites the opened file; Save As... writes
a new YAML next to it (or wherever the user points the file dialog).
"""

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QMessageBox,
    QVBoxLayout,
)

from .config_form import ConfigForm


class ParamsDialog(QDialog):
    saved = Signal(Path)  # emitted after every successful write

    def __init__(self, path: Path, parent=None):
        super().__init__(parent)
        self.path = Path(path)
        self.setWindowTitle(f"Parameters - {self.path.name}")
        from .widgets import fit_to_screen
        fit_to_screen(self, 560, 720)
        self.form = ConfigForm()
        self.form.load(self.path)

        buttons = QDialogButtonBox(QDialogButtonBox.Save
                                   | QDialogButtonBox.Close)
        self.save_as_btn = buttons.addButton("Save As...",
                                             QDialogButtonBox.ActionRole)
        buttons.button(QDialogButtonBox.Save).clicked.connect(self.save)
        self.save_as_btn.clicked.connect(self.save_as)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.form)
        layout.addWidget(buttons)

    def _write(self, path: Path) -> bool:
        try:
            self.form.save(path)
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid parameters", str(exc))
            return False
        self.saved.emit(Path(path))
        return True

    def save(self) -> None:
        """Overwrite the file this dialog was opened on."""
        if self._write(self.path):
            self.accept()

    def save_as(self) -> None:
        """Write the form to a new YAML file (rename-and-keep-original)."""
        target, _ = QFileDialog.getSaveFileName(
            self, "Save config as", str(self.path.with_name(
                f"{self.path.stem}_copy.yaml")),
            "YAML (*.yaml);;All files (*)")
        if not target:
            return
        target = Path(target)
        if target.suffix not in (".yaml", ".yml"):
            target = target.with_suffix(".yaml")
        if self._write(target):
            self.accept()
