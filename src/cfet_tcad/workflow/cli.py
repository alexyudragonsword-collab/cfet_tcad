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

    struct_p = sub.add_parser(
        "structure",
        help="build the mesh and export the doped structure to VTK "
             "without solving (Structure Editor-style preview)")
    struct_p.add_argument("config", type=Path)
    struct_p.add_argument("-o", "--output", type=Path, default=None)
    struct_p.add_argument("--png", type=Path, default=None,
                          help="also render a 3D image (requires pyvista)")
    struct_p.add_argument("--stl", type=Path, default=None,
                          help="export the device surface as STL "
                               "(.ply/.vtp also work; no GL needed)")
    struct_p.add_argument("--obj", type=Path, default=None,
                          help="export a material-colored OBJ + MTL "
                               "(needs GL, like --png)")

    sweep_p = sub.add_parser(
        "sweep", help="parametric sweep: one process per point")
    sweep_p.add_argument("config", type=Path)
    point_src = sweep_p.add_mutually_exclusive_group(required=True)
    point_src.add_argument("-p", "--param", action="append",
                           metavar="PATH=V1,V2,...",
                           help="e.g. device.l_gate_nm=12,15,18 "
                                "(repeat for a cartesian product)")
    point_src.add_argument("--points", type=Path, default=None,
                           metavar="CSV",
                           help="design-point table: one row per run, "
                                "dotted config paths as headers "
                                "(an edited sweep_summary.csv works)")
    sweep_p.add_argument("-j", "--jobs", type=int, default=1)
    sweep_p.add_argument("-o", "--output", type=Path, default=None)
    sweep_p.add_argument("--zip", action="store_true", dest="zip_params",
                         help="advance the -p value lists together as "
                              "paired tuples instead of taking the "
                              "cartesian product")

    args = parser.parse_args(argv)

    if args.command == "sweep":
        from .config import load_config
        from .sweep import load_points_csv, parse_param_spec, run_sweep
        params = points = None
        if args.points is not None:
            points = load_points_csv(args.points)
        else:
            params = dict(parse_param_spec(s) for s in args.param)
        cfg = load_config(args.config)
        out = Path(args.output or f"{cfg.output.directory}_sweep")
        rows = run_sweep(args.config, params, out, jobs=args.jobs,
                         zip_params=args.zip_params, points=points)
        n_ok = sum(1 for r in rows if r.get("status") == "ok")
        print(f"{n_ok}/{len(rows)} points completed; summary in {out}/")
        return 0 if n_ok == len(rows) else 1

    from .config import load_config
    cfg = load_config(args.config)

    if args.command == "mesh":
        from ..geometry import BUILDERS
        out = Path(args.output or cfg.output.directory)
        msh = out / f"{cfg.device.name}.msh"
        BUILDERS[cfg.device.structure](cfg.device, cfg.mesh).build(msh)
        print(f"mesh written: {msh}")
        return 0

    if args.command == "structure":
        import devsim

        from ..geometry import BUILDERS
        from ..meshio_devsim import load_mesh
        from ..physics.doping import create_doping_from_spec

        out = Path(args.output or cfg.output.directory)
        out.mkdir(parents=True, exist_ok=True)
        msh = out / f"{cfg.device.name}.msh"
        layout = BUILDERS[cfg.device.structure](cfg.device, cfg.mesh).build(msh)
        device = load_mesh(msh, layout, cfg.device.name)
        for region, material in layout.regions.items():
            if material == "Silicon":
                polarity = layout.silicon_polarity.get(
                    region, cfg.device.polarity)
                create_doping_from_spec(
                    device, region, cfg.device, polarity=polarity,
                    spec=layout.doping_specs.get(region))
        vtk_dir = out / "vtk"
        vtk_dir.mkdir(exist_ok=True)
        devsim.write_devices(file=str(vtk_dir / "structure"), type="vtk")
        print(f"structure written: {vtk_dir}/")
        if args.png:
            from ..io.render3d import render_structure
            render_structure(vtk_dir, png=args.png, field="NetDoping")
            print(f"rendered: {args.png}")
        if args.stl:
            from ..io.render3d import export_surface
            print(f"surface exported: {export_surface(vtk_dir, args.stl)}")
        if args.obj:
            from ..io.render3d import export_obj
            print(f"OBJ exported: {export_obj(vtk_dir, args.obj)}")
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
