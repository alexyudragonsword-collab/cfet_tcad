"""GUI entry point: ``cfet-tcad-gui [project_root]``."""

import sys
from pathlib import Path


def main(argv=None) -> int:
    from PySide6.QtWidgets import QApplication

    from .main_window import MainWindow

    argv = list(sys.argv if argv is None else argv)
    root = Path(argv[1]) if len(argv) > 1 else Path.cwd()
    app = QApplication(argv)
    window = MainWindow(project_root=root)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
