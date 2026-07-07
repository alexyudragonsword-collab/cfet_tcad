"""SWB-style experiment table: one row per run, node-status colors."""

from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor

# Sentaurus Workbench node colors
STATUS_COLORS = {
    "pending": QColor("#e8eaed"),  # added, waits for its Run button
    "queued": QColor("#d0d0d0"),
    "running": QColor("#f4d03f"),
    "done": QColor("#7dcea0"),
    "failed": QColor("#ec7063"),
    "stopped": QColor("#aab7c4"),
}

COLUMNS = ("Experiment", "Parameters", "Status", "Actions",
           "Vt [V]", "SS [mV/dec]", "Ion [A]", "Ioff [A]", "DIBL [mV/V]",
           "Changes")


@dataclass(eq=False)  # identity semantics: hashable, usable as dict key
class Experiment:
    name: str
    config_path: Path
    out_dir: Path
    overrides: dict = field(default_factory=dict)
    status: str = "pending"
    fom: dict = field(default_factory=dict)  # summarized, keys ~ COLUMNS[3:]
    progress: float | None = None  # 0..1 while running (parsed from CLI)
    #: the original configs/*.yaml this run derives from (for the diff)
    base_config: Path | None = None
    #: human-readable diff of config_path vs base_config ("Changes" column)
    changes: str = ""


def fom_summary(fom: dict) -> dict:
    """Map a fom.json payload (idvg / cfet_idvg / vtc variants) onto the
    table columns.  For multi-curve results the saturation (largest |Vd|)
    entry wins; for CFET stacks the nFET is shown."""
    if not fom:
        return {}
    if "vm_v" in fom:  # inverter VTC
        return {"Vt [V]": fom.get("vm_v"),
                "SS [mV/dec]": fom.get("max_gain"),
                "Ion [A]": fom.get("voh_v"),
                "Ioff [A]": fom.get("vol_v")}
    node = fom.get("nFET", fom)
    best, best_vd = None, -1.0
    for key, value in node.items():
        if isinstance(value, dict) and "ss_mv_per_dec" in value:
            vd = abs(value.get("vdd_v") or 0.0)
            if vd > best_vd:
                best, best_vd = value, vd
    if best is None and "ss_mv_per_dec" in node:
        best = node
    if best is None:
        return {}
    out = {"Vt [V]": best.get("vt_constant_current_v"),
           "SS [mV/dec]": best.get("ss_mv_per_dec"),
           "Ion [A]": best.get("ion_a"),
           "Ioff [A]": best.get("ioff_a")}
    dibl = fom.get("dibl_mv_per_v")
    if dibl is not None:
        out["DIBL [mV/V]"] = dibl
    return out


class ExperimentModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.experiments: list[Experiment] = []

    # --- Qt model protocol -------------------------------------------------

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.experiments)

    def columnCount(self, parent=QModelIndex()):
        return len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return COLUMNS[section]
        if role == Qt.DisplayRole:
            return str(section + 1)
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        exp = self.experiments[index.row()]
        col = COLUMNS[index.column()]
        if role == Qt.DisplayRole:
            if col == "Experiment":
                return exp.name
            if col == "Parameters":
                return ", ".join(f"{k.split('.')[-1]}={v}"
                                 for k, v in exp.overrides.items()) or "-"
            if col == "Status":
                if exp.status == "running" and exp.progress is not None:
                    return f"running {exp.progress:.0%}"
                return exp.status
            if col == "Actions":  # rendered by per-row index widgets
                return None
            if col == "Changes":
                return exp.changes or "-"
            value = exp.fom.get(col)
            if value is None:
                return ""
            return f"{value:.4g}" if isinstance(value, float) else str(value)
        if role == Qt.BackgroundRole and col == "Status":
            return STATUS_COLORS.get(exp.status)
        return None

    # --- mutation helpers ---------------------------------------------------

    def add(self, exp: Experiment) -> int:
        row = len(self.experiments)
        self.beginInsertRows(QModelIndex(), row, row)
        self.experiments.append(exp)
        self.endInsertRows()
        return row

    def update_row(self, row: int) -> None:
        self.dataChanged.emit(self.index(row, 0),
                              self.index(row, len(COLUMNS) - 1))

    def row_of(self, exp: Experiment) -> int:
        return self.experiments.index(exp)

    def remove(self, row: int) -> None:
        """Drop a table row (files on disk are untouched)."""
        self.beginRemoveRows(QModelIndex(), row, row)
        del self.experiments[row]
        self.endRemoveRows()
