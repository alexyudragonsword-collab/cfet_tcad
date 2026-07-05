"""GUI entry point: ``cfet-tcad-gui [project_root]``."""

import sys
from pathlib import Path


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
    root = Path(argv[1]) if len(argv) > 1 else Path.cwd()
    app = QApplication(argv)
    app.setWindowIcon(app_icon())  # inherited by all windows
    window = MainWindow(project_root=root)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
