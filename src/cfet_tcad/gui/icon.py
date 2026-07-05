"""Application icon (window/taskbar branding)."""

from importlib import resources
from pathlib import Path


def icon_path() -> Path:
    return Path(resources.files("cfet_tcad.gui") / "icons" / "app.png")


def app_icon():
    """QIcon of the STACKED CMOS TCAD logo (null icon if the file is
    missing, e.g. a stripped-down install)."""
    from PySide6.QtGui import QIcon

    path = icon_path()
    return QIcon(str(path)) if path.exists() else QIcon()
