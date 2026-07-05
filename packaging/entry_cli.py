"""PyInstaller entry: cfet-tcad.exe (console CLI, also spawned by the GUI
for each simulation process)."""

import sys

from cfet_tcad.workflow.cli import main

if __name__ == "__main__":
    sys.exit(main())
