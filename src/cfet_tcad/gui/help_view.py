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
MANUALS = {"English": "manual.html", "中文": "manual_zh.html"}


def _help_file(name: str) -> Path:
    return Path(resources.files("cfet_tcad.gui") / "help" / name)


def guide_path(language: str = "English") -> Path:
    return _help_file(GUIDES.get(language, "guide.html"))


def manual_path(language: str = "English") -> Path:
    return _help_file(MANUALS.get(language, "manual.html"))


def _default_language() -> str:
    if QLocale.system().language() == QLocale.Language.Chinese:
        return "中文"
    return "English"


class HelpView(QWidget):
    """A language-toggled HTML document viewer.  Defaults to the user
    guide; pass ``docs`` (language -> filename) and ``title`` to reuse
    the same toggle machinery for other documents (e.g. the manual)."""

    def __init__(self, docs: dict | None = None,
                 title: str = "User Guide / 用户指南", parent=None):
        super().__init__(parent)
        self.docs = docs or GUIDES
        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        self.lang_box = QComboBox()
        self.lang_box.addItems(list(self.docs))
        self.lang_box.setCurrentText(_default_language())
        self.lang_box.currentTextChanged.connect(self.set_language)

        bar = QHBoxLayout()
        bar.setContentsMargins(6, 4, 6, 0)
        bar.addWidget(QLabel(title))
        bar.addStretch(1)
        bar.addWidget(QLabel("Language"))
        bar.addWidget(self.lang_box)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(bar)
        layout.addWidget(self.browser)

        self.set_language(self.lang_box.currentText())

    def set_language(self, language: str) -> None:
        path = _help_file(self.docs.get(language, next(iter(self.docs.values()))))
        if path.exists():
            # read explicitly as UTF-8 (Windows would otherwise guess a
            # legacy codepage) and keep a base URL so img/ paths resolve
            self.browser.document().setBaseUrl(
                QUrl.fromLocalFile(str(path.parent) + "/"))
            self.browser.setHtml(path.read_text(encoding="utf-8"))
        else:  # pragma: no cover - packaging error surface
            self.browser.setPlainText(f"user guide not found: {path}")
