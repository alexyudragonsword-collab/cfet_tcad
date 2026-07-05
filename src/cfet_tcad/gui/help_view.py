"""Illustrated user guide rendered in-app (QTextBrowser, no web engine).

Ships in English and Chinese; the default follows the system locale and a
toggle in the corner switches languages.
"""

from importlib import resources
from pathlib import Path

from PySide6.QtCore import QLocale, QUrl
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

GUIDES = {"English": "guide.html", "中文": "guide_zh.html"}


def guide_path(language: str = "English") -> Path:
    name = GUIDES.get(language, "guide.html")
    return Path(resources.files("cfet_tcad.gui") / "help" / name)


def _default_language() -> str:
    if QLocale.system().language() == QLocale.Language.Chinese:
        return "中文"
    return "English"


class HelpView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        self.lang_box = QComboBox()
        self.lang_box.addItems(list(GUIDES))
        self.lang_box.setCurrentText(_default_language())
        self.lang_box.currentTextChanged.connect(self.set_language)

        bar = QHBoxLayout()
        bar.setContentsMargins(6, 4, 6, 0)
        bar.addWidget(QLabel("User Guide / 用户指南"))
        bar.addStretch(1)
        bar.addWidget(QLabel("Language"))
        bar.addWidget(self.lang_box)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(bar)
        layout.addWidget(self.browser)

        self.set_language(self.lang_box.currentText())

    def set_language(self, language: str) -> None:
        path = guide_path(language)
        if path.exists():
            self.browser.setSource(QUrl.fromLocalFile(str(path)))
        else:  # pragma: no cover - packaging error surface
            self.browser.setPlainText(f"user guide not found: {path}")
