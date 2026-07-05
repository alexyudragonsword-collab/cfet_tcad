"""Command-line interface: ``cfet-tcad run <config.yaml>``."""

import argparse
import json
import sys
from pathlib import Path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="cfet-tcad",
        description="CFET / nanosheet TCAD simulation system "
                    "(DEVSIM + gmsh, VTK output for VisIt)")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="run a simulation from a YAML config")
    run_p.add_argument("config", type=Path)
    run_p.add_argument("-o", "--output", type=Path, default=None,
                       help="override output directory")

    mesh_p = sub.add_parser("mesh", help="only generate the gmsh mesh")
    mesh_p.add_argument("config", type=Path)
    mesh_p.add_argument("-o", "--output", type=Path, default=None)

    args = parser.parse_args(argv)

    from .config import load_config
    cfg = load_config(args.config)

    if args.command == "mesh":
        from ..geometry import Nanosheet2DBuilder
        out = Path(args.output or cfg.output.directory)
        msh = out / f"{cfg.device.name}.msh"
        Nanosheet2DBuilder(cfg.device, cfg.mesh).build(msh)
        print(f"mesh written: {msh}")
        return 0

    from .runner import run_config
    results = run_config(cfg, args.output)
    if "fom" in results:
        print(json.dumps(results["fom"], indent=2, sort_keys=True))
    out = Path(args.output or cfg.output.directory)
    print(f"results written to: {out}/", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
