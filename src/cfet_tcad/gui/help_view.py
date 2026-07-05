"""Illustrated user guide rendered in-app (QTextBrowser, no web engine)."""

from importlib import resources
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QTextBrowser, QVBoxLayout, QWidget


def guide_path() -> Path:
    return Path(resources.files("cfet_tcad.gui") / "help" / "guide.html")


class HelpView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        path = guide_path()
        if path.exists():
            # base URL from the file location so img/... resolves
            self.browser.setSource(QUrl.fromLocalFile(str(path)))
        else:  # pragma: no cover - packaging error surface
            self.browser.setPlainText(f"user guide not found: {path}")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.browser)
