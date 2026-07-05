"""Tabular and graphical result output: CSV IV data and matplotlib plots."""

import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def write_iv_csv(path: Path, rows: list[dict]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise ValueError("no data rows to write")
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return path


def write_json(path: Path, data: dict) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    return path


def plot_idvg(path: Path, curves: list[dict], title: str = "") -> Path:
    """Transfer characteristics: log|Id| (left) and linear |Id| (right).

    ``curves``: [{"vg": [...], "id": [...], "label": str}, ...]
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig, (ax_log, ax_lin) = plt.subplots(1, 2, figsize=(10, 4.2))
    for c in curves:
        vg, iabs = c["vg"], [abs(i) for i in c["id"]]
        ax_log.semilogy(vg, iabs, marker="o", ms=3, label=c.get("label", ""))
        ax_lin.plot(vg, iabs, marker="o", ms=3, label=c.get("label", ""))
    for ax, ylabel in ((ax_log, "|Id| [A] (log)"), (ax_lin, "|Id| [A]")):
        ax.set_xlabel("Vg [V]")
        ax.set_ylabel(ylabel)
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=8)
    fig.suptitle(title)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def plot_vtc(path: Path, vin: list, vout: list, i_dd: list,
             title: str = "") -> Path:
    """Inverter voltage transfer characteristic + supply current."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig, (ax_v, ax_i) = plt.subplots(1, 2, figsize=(10, 4.2))
    ax_v.plot(vin, vout, marker="o", ms=3)
    ax_v.plot(vin, vin, ls=":", c="gray", lw=1)  # vout = vin guide
    ax_v.set_xlabel("Vin [V]")
    ax_v.set_ylabel("Vout [V]")
    ax_v.grid(True, alpha=0.3)
    ax_i.semilogy(vin, [abs(i) for i in i_dd], marker="o", ms=3, color="C1")
    ax_i.set_xlabel("Vin [V]")
    ax_i.set_ylabel("|I_DD| [A] (log)")
    ax_i.grid(True, alpha=0.3)
    fig.suptitle(title)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def plot_idvd(path: Path, curves: list[dict], title: str = "") -> Path:
    """Output characteristics: |Id| vs Vd for a set of Vg values."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(6, 4.2))
    for c in curves:
        ax.plot(c["vd"], [abs(i) for i in c["id"]], marker="o", ms=3,
                label=c.get("label", ""))
    ax.set_xlabel("Vd [V]")
    ax.set_ylabel("|Id| [A]")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8)
    fig.suptitle(title)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path
