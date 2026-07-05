"""Nuitka entry: single-executable dispatcher.

Nuitka compiles one binary per run, so instead of two executables the
bundle ships one ``cfet-tcad.exe``: with CLI arguments it behaves as the
command line tool, without arguments it launches the workbench GUI.
The GUI's child simulation processes re-invoke this same executable
(gui.run_queue.cli_command falls back to sys.executable when no sibling
CLI exe exists).  Built with --windows-console-mode=attach so console
output appears when run from a terminal but no console window pops up on
double-click.
"""

import sys

if not getattr(sys, "frozen", False):
    sys.frozen = True  # older Nuitka versions do not set it


def main() -> int:
    if len(sys.argv) > 1:
        from cfet_tcad.workflow.cli import main as cli_main
        return cli_main()
    from cfet_tcad.gui.app import main as gui_main
    return gui_main()


if __name__ == "__main__":
    sys.exit(main())
