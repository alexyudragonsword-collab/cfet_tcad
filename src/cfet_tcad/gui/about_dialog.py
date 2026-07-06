"""About dialog: version, author, and component credits."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout

import cfet_tcad

ABOUT_HTML = f"""
<h2>{cfet_tcad.__app_name__}</h2>
<p><b>Version {cfet_tcad.__version__}</b></p>
<p>Open-source CFET / stacked-nanosheet TCAD simulation system,<br>
patterned on the Synopsys Sentaurus tool chain.</p>
<p><b>Author:</b> {cfet_tcad.__author__}</p>
<p>Built on
<a href="https://devsim.org">DEVSIM</a> (drift-diffusion solver),
<a href="https://gmsh.info">gmsh</a> (meshing),
<a href="https://pyvista.org">PyVista</a>/VTK (3D rendering),
PySide6/Qt, and matplotlib.</p>
<hr>
<p>{cfet_tcad.__copyright__}<br>
Licensed under the Apache License, Version 2.0.</p>
<p><i>This software is provided "as is", without warranty of any kind.
It is a research / educational device-level TCAD tool and is not
intended for production process or layout sign-off.</i></p>
"""


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"About {cfet_tcad.__app_name__}")
        label = QLabel(ABOUT_HTML)
        label.setTextFormat(Qt.RichText)
        label.setOpenExternalLinks(True)
        label.setAlignment(Qt.AlignCenter)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok)
        buttons.accepted.connect(self.accept)
        layout = QVBoxLayout(self)
        layout.addWidget(label)
        layout.addWidget(buttons)
