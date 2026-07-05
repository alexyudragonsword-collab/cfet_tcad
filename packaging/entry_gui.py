"""PyInstaller entry: cfet-tcad-gui.exe (windowed workbench)."""

import sys

from cfet_tcad.gui.app import main

if __name__ == "__main__":
    sys.exit(main())
