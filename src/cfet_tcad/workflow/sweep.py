"""Parametric sweep / DOE engine (Sentaurus Workbench analog).

Runs the full pipeline once per point of a (cartesian-product) parameter
grid, each point in its own OS process — DEVSIM keeps global state, so
``maxtasksperchild=1`` guarantees every simulation starts from a clean
interpreter.  Results land in per-point subdirectories plus a flattened
``sweep_summary.csv`` / ``sweep_summary.json``; 1D sweeps of an Id-Vg
experiment additionally get a trend plot of the key figures of merit.

CLI:  cfet-tcad sweep base.yaml -p device.l_gate_nm=12,15,18,21 -j 4
"""

import csv
import itertools
import json
import multiprocessing as mp
import os
from pathlib import Path


def _coerce(value: str):
    """CSV/CLI string -> int, float, or str (in that preference order)."""
    value = value.strip()
    try:
        return int(value)
    except ValueError:
        try:
            return float(value)
        except ValueError:
            return value


def parse_param_spec(spec: str) -> tuple[str, list]:
    """'device.l_gate_nm=12,15,18' -> ('device.l_gate_nm', [12.0, 15.0, 18.0])"""
    if "=" not in spec:
        raise ValueError(f"expected PATH=v1,v2,... got {spec!r}")
    path, _, values = spec.partition("=")
    parsed = [_coerce(v) for v in values.split(",")]
    if not parsed:
        raise ValueError(f"no values in {spec!r}")
    return path.strip(), parsed


#: config sections a CSV column must start with to count as a parameter
CONFIG_SECTIONS = ("device", "mesh", "physics", "simulation", "output",
                   "extract")


def load_points_csv(path: Path) -> list[dict]:
    """Design-point import: one row per simulation, columns are dotted
    config paths (device.l_gate_nm, physics.mobility_model, ...).

    Columns whose first path segment is not a config section are ignored
    (with a notice) - so an exported ``sweep_summary.csv`` can be edited
    and fed straight back in; its status/FOM columns just drop out.
    """
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError(f"{path}: empty CSV")
        cols = [c.strip() for c in reader.fieldnames]
        params = [c for c in cols if c.split(".")[0] in CONFIG_SECTIONS]
        ignored = [c for c in cols if c not in params]
        if not params:
            raise ValueError(
                f"{path}: no parameter columns; headers must be dotted "
                f"config paths starting with one of {CONFIG_SECTIONS}")
        if ignored:
            print(f"ignoring non-parameter column(s): {ignored}")
        points = []
        for row in reader:
            cleaned = {(k or "").strip(): (v or "") for k, v in row.items()}
            point = {c: _coerce(cleaned[c]) for c in params
                     if cleaned.get(c, "").strip() != ""}
            if point:
                points.append(point)
    if not points:
        raise ValueError(f"{path}: no data rows")
    return points


def points_to_zip_specs(points: list[dict]) -> list[str]:
    """Rewrite a point list as ``path=v1,v2,...`` lines (zip semantics),
    the form the GUI sweep dialog edits.  Missing cells repeat the
    column's previous value so all lists stay equally long."""
    columns = list(dict.fromkeys(k for p in points for k in p))
    lines = []
    for col in columns:
        values, last = [], ""
        for p in points:
            last = p.get(col, last)
            values.append(str(last))
        lines.append(f"{col}={','.join(values)}")
    return lines


def _flatten(prefix: str, obj, out: dict) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            _flatten(f"{prefix}{k}." if prefix else f"{k}.", v, out)
        return
    out[prefix.rstrip(".")] = obj


def flatten_fom(fom: dict) -> dict:
    out = {}
    _flatten("", fom, out)
    return out


def _run_point(args) -> dict:
    """Worker: one simulation in a fresh process; solver spam goes to a
    per-point log (fd-level redirect — DEVSIM prints from C++)."""
    base_config, overrides, point_dir = args
    point_dir = Path(point_dir)
    point_dir.mkdir(parents=True, exist_ok=True)
    log = os.open(point_dir / "run.log", os.O_WRONLY | os.O_CREAT | os.O_TRUNC)
    os.dup2(log, 1)
    os.dup2(log, 2)
    os.close(log)

    from .config import load_config
    from .runner import run_config

    row = dict(overrides)
    try:
        cfg = load_config(Path(base_config), overrides=overrides)
        results = run_config(cfg, output_dir=point_dir)
        row.update(flatten_fom(results.get("fom", {})))
        row["status"] = "ok"
    except Exception as exc:  # noqa: BLE001 - report, don't kill the sweep
        row["status"] = f"error: {exc}"
    return row


def run_sweep(base_config: Path, params: dict | None, out_dir: Path,
              jobs: int = 1, zip_params: bool = False,
              points: list[dict] | None = None) -> list[dict]:
    """Run a parameter grid: the cartesian product of ``params``
    (path -> value list), or — with ``zip_params`` — the value lists
    advanced together as paired tuples (all lists must be equally long;
    used for coupled knobs such as a Ge-fraction sweep that must retune
    the gate workfunction at each composition to hold Vt).

    Alternatively pass explicit ``points`` (one override dict per
    simulation, e.g. from :func:`load_points_csv`) instead of a grid.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if (points is None) == (params is None):
        raise ValueError("pass exactly one of params or points")
    paired = zip_params or points is not None
    if points is not None:
        names = list(dict.fromkeys(k for p in points for k in p))
        # per-column value lists drive the trend-plot axis pick below
        params = {n: [p[n] for p in points if n in p] for n in names}
    else:
        names = list(params)
        if zip_params:
            lengths = {n: len(params[n]) for n in names}
            if len(set(lengths.values())) > 1:
                raise ValueError(
                    f"--zip requires equally long value lists, got {lengths}")
            points = [dict(zip(names, combo))
                      for combo in zip(*(params[n] for n in names))]
        else:
            points = [dict(zip(names, combo)) for combo in
                      itertools.product(*(params[n] for n in names))]
    tasks = []
    for i, overrides in enumerate(points):
        tag = "_".join(f"{p.split('.')[-1]}{v}" for p, v in overrides.items())
        tasks.append((str(base_config), overrides, str(out_dir / f"p{i:03d}_{tag}")))

    if jobs > 1:
        ctx = mp.get_context("spawn")
        with ctx.Pool(processes=jobs, maxtasksperchild=1) as pool:
            rows = pool.map(_run_point, tasks)
    else:
        ctx = mp.get_context("spawn")
        rows = []
        for t in tasks:  # still one process per point (devsim global state)
            with ctx.Pool(processes=1, maxtasksperchild=1) as pool:
                rows.append(pool.map(_run_point, [t])[0])

    _write_summary(out_dir, names, rows)
    # trend plot: 1D numeric sweeps, or paired point lists (zip / CSV
    # import) keyed on the first all-numeric parameter axis
    axis = None
    if len(names) == 1 or paired:
        for n in names:
            if all(isinstance(v, (int, float)) for v in params[n]):
                axis = n
                break
    if axis:
        _plot_trends(out_dir, axis, rows)
    return rows


def _write_summary(out_dir: Path, names: list, rows: list[dict]) -> None:
    keys = list(dict.fromkeys(k for row in rows for k in row))
    with open(out_dir / "sweep_summary.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys, restval="")
        writer.writeheader()
        writer.writerows(rows)
    with open(out_dir / "sweep_summary.json", "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, sort_keys=True)


# FOM suffixes plotted for 1D Id-Vg sweeps (matched against flattened keys)
_TREND_METRICS = (
    ("ss_mv_per_dec", "SS [mV/dec]", "linear"),
    ("dibl_mv_per_v", "DIBL [mV/V]", "linear"),
    ("vt_constant_current_v", "Vt (const-current) [V]", "linear"),
    ("ion_ioff_ratio", "Ion/Ioff", "log"),
)


def _pick_metric(row: dict, suffix: str):
    """Prefer the saturation (largest |Vd|) curve's figure when several
    bias labels carry the same metric."""
    candidates = [(k, v) for k, v in row.items() if k.endswith(suffix)
                  and isinstance(v, (int, float))]
    if not candidates:
        return None
    return sorted(candidates, key=lambda kv: kv[0])[-1][1]


def _plot_trends(out_dir: Path, param: str, rows: list[dict]) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ok = [r for r in rows if r.get("status") == "ok"]
    if len(ok) < 2:
        return
    x = [r[param] for r in ok]
    fig, axes = plt.subplots(2, 2, figsize=(9, 6.5))
    for ax, (suffix, label, scale) in zip(axes.flat, _TREND_METRICS):
        y = [_pick_metric(r, suffix) for r in ok]
        if any(v is None for v in y):
            ax.axis("off")
            continue
        ax.plot(x, y, marker="o")
        ax.set_xlabel(param)
        ax.set_ylabel(label)
        ax.set_yscale(scale)
        ax.grid(True, alpha=0.3)
    fig.suptitle(f"sweep: {param}")
    fig.tight_layout()
    fig.savefig(out_dir / "sweep_trends.png", dpi=150)
    plt.close(fig)
