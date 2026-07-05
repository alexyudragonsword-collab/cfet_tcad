"""Solver output console with SWB-style noise filtering."""

import re

from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QPlainTextEdit, QVBoxLayout, QWidget

_NOISE = re.compile(
    r"RelError|AbsError|^\s*Equation|^\s*Region|^\s*Device|^Iteration")


class LogConsole(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setMaximumBlockCount(5000)
        self.verbose = QCheckBox("verbose solver output")
        bar = QHBoxLayout()
        bar.addWidget(QLabel("Log"))
        bar.addStretch(1)
        bar.addWidget(self.verbose)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.addLayout(bar)
        layout.addWidget(self.text)

    def append(self, line: str) -> None:
        if not self.verbose.isChecked() and _NOISE.search(line):
            return
        self.text.appendPlainText(line)
