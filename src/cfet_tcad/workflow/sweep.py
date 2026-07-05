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


def parse_param_spec(spec: str) -> tuple[str, list]:
    """'device.l_gate_nm=12,15,18' -> ('device.l_gate_nm', [12.0, 15.0, 18.0])"""
    if "=" not in spec:
        raise ValueError(f"expected PATH=v1,v2,... got {spec!r}")
    path, _, values = spec.partition("=")
    parsed = []
    for v in values.split(","):
        v = v.strip()
        try:
            parsed.append(int(v))
        except ValueError:
            try:
                parsed.append(float(v))
            except ValueError:
                parsed.append(v)
    if not parsed:
        raise ValueError(f"no values in {spec!r}")
    return path.strip(), parsed


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


def run_sweep(base_config: Path, params: dict, out_dir: Path,
              jobs: int = 1) -> list[dict]:
    """Run the cartesian product of ``params`` (path -> value list)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    names = list(params)
    points = [dict(zip(names, combo))
              for combo in itertools.product(*(params[n] for n in names))]
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
    if len(names) == 1 and all(isinstance(v, (int, float))
                               for v in params[names[0]]):
        _plot_trends(out_dir, names[0], rows)
    return rows


def _write_summary(out_dir: Path, names: list, rows: list[dict]) -> None:
    keys = list(dict.fromkeys(k for row in rows for k in row))
    with open(out_dir / "sweep_summary.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys, restval="")
        writer.writeheader()
        writer.writerows(rows)
    with open(out_dir / "sweep_summary.json", "w") as f:
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
