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

    sweep_p = sub.add_parser(
        "sweep", help="parametric sweep: one process per point")
    sweep_p.add_argument("config", type=Path)
    sweep_p.add_argument("-p", "--param", action="append", required=True,
                         metavar="PATH=V1,V2,...",
                         help="e.g. device.l_gate_nm=12,15,18 "
                              "(repeat for a cartesian product)")
    sweep_p.add_argument("-j", "--jobs", type=int, default=1)
    sweep_p.add_argument("-o", "--output", type=Path, default=None)
    sweep_p.add_argument("--zip", action="store_true", dest="zip_params",
                         help="advance the -p value lists together as "
                              "paired tuples instead of taking the "
                              "cartesian product")

    args = parser.parse_args(argv)

    if args.command == "sweep":
        from .config import load_config
        from .sweep import parse_param_spec, run_sweep
        params = dict(parse_param_spec(s) for s in args.param)
        cfg = load_config(args.config)
        out = Path(args.output or f"{cfg.output.directory}_sweep")
        rows = run_sweep(args.config, params, out, jobs=args.jobs,
                         zip_params=args.zip_params)
        n_ok = sum(1 for r in rows if r.get("status") == "ok")
        print(f"{n_ok}/{len(rows)} points completed; summary in {out}/")
        return 0 if n_ok == len(rows) else 1

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
