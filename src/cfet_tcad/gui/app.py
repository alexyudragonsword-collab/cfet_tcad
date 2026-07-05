"""GUI entry point: ``cfet-tcad-gui [project_root]``."""

import sys
from pathlib import Path


def default_project_root(argv: list, frozen: bool, exe_dir: Path) -> Path:
    """Project root for the config browser: an explicit argument wins;
    otherwise the working directory - except in a frozen bundle launched
    by double-click (cwd is arbitrary), where the install directory has
    the shipped example configs sitting next to the exe."""
    if len(argv) > 1:
        return Path(argv[1])
    cwd = Path.cwd()
    if frozen and not (cwd / "configs").is_dir() \
            and (exe_dir / "configs").is_dir():
        return exe_dir
    return cwd


def main(argv=None) -> int:
    from PySide6.QtWidgets import QApplication

    from .icon import app_icon
    from .main_window import MainWindow

    if sys.platform == "win32":
        # give the process its own taskbar identity so Windows shows the
        # app icon instead of the Python interpreter's
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "YuRui.StackedCmosTcad")

    argv = list(sys.argv if argv is None else argv)
    root = default_project_root(argv, getattr(sys, "frozen", False),
                                Path(sys.executable).parent)
    app = QApplication(argv)
    app.setWindowIcon(app_icon())  # inherited by all windows
    window = MainWindow(project_root=root)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
