"""Results viewer (Sentaurus Visual / Inspect analog): interactive
matplotlib canvas re-plotting the run's CSV curves plus a flattened
figure-of-merit table."""

import csv
import json
from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

# import the Qt canvas directly (no matplotlib.use(): that path insists on
# a display even under Qt's offscreen platform, and we never touch pyplot)
from matplotlib.backends.backend_qtagg import (
    FigureCanvasQTAgg,
    NavigationToolbar2QT,
)
from matplotlib.figure import Figure

from ..workflow.sweep import flatten_fom


def _read_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [{k: float(v) for k, v in row.items()}
                for row in csv.DictReader(f)]


class ResultsView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.figure = Figure(figsize=(6, 4))
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.log_toggle = QCheckBox("log |I|")
        self.log_toggle.setChecked(True)
        self.log_toggle.toggled.connect(self._replot)
        self.title = QLabel("no results loaded")
        self.fom_table = QTableWidget(0, 2)
        self.fom_table.setHorizontalHeaderLabels(["figure of merit", "value"])
        self.fom_table.horizontalHeader().setStretchLastSection(True)

        top = QWidget()
        bar = QHBoxLayout(top)
        bar.setContentsMargins(4, 4, 4, 0)
        bar.addWidget(self.title)
        bar.addStretch(1)
        bar.addWidget(self.log_toggle)

        plot_panel = QWidget()
        pv = QVBoxLayout(plot_panel)
        pv.setContentsMargins(0, 0, 0, 0)
        pv.addWidget(top)
        pv.addWidget(NavigationToolbar2QT(self.canvas, self))
        pv.addWidget(self.canvas, stretch=1)

        split = QSplitter()
        split.addWidget(plot_panel)
        split.addWidget(self.fom_table)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(split)

        self._dir: Path | None = None

    # --- loading --------------------------------------------------------

    def load_dir(self, out_dir: Path) -> None:
        self._dir = Path(out_dir)
        self.title.setText(str(self._dir))
        self._replot()
        self._load_fom()

    def _load_fom(self) -> None:
        self.fom_table.setRowCount(0)
        path = self._dir / "fom.json"
        if not path.exists():
            return
        flat = flatten_fom(json.loads(path.read_text(encoding="utf-8")))
        for key, value in sorted(flat.items()):
            row = self.fom_table.rowCount()
            self.fom_table.insertRow(row)
            self.fom_table.setItem(row, 0, QTableWidgetItem(key))
            text = f"{value:.5g}" if isinstance(value, float) else str(value)
            self.fom_table.setItem(row, 1, QTableWidgetItem(text))

    # --- plotting --------------------------------------------------------

    def _replot(self) -> None:
        self.figure.clear()
        if self._dir is None:
            self.canvas.draw_idle()
            return
        ax = self.figure.add_subplot(111)
        log = self.log_toggle.isChecked()
        for name, plotter in (("idvg.csv", self._plot_idvg),
                              ("cfet_idvg.csv", self._plot_cfet),
                              ("idvd.csv", self._plot_idvd),
                              ("vtc.csv", self._plot_vtc)):
            path = self._dir / name
            if path.exists():
                plotter(ax, _read_csv(path), log)
                break
        else:
            ax.set_title("no curve data found")
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=8)
        self.figure.tight_layout()
        self.canvas.draw_idle()

    @staticmethod
    def _series(rows, key):
        groups: dict = {}
        for r in rows:
            groups.setdefault(r[key], []).append(r)
        return groups

    def _plot_idvg(self, ax, rows, log):
        for vd, pts in sorted(self._series(rows, "vd_v").items()):
            x = [p["vg_v"] for p in pts]
            y = [abs(p["id_a"]) for p in pts]
            (ax.semilogy if log else ax.plot)(x, y, "o-", ms=3,
                                              label=f"Vd = {vd:+.2f} V")
        ax.set_xlabel("Vg [V]")
        ax.set_ylabel("|Id| [A]")

    def _plot_idvd(self, ax, rows, log):
        for vg, pts in sorted(self._series(rows, "vg_v").items()):
            x = [p["vd_v"] for p in pts]
            y = [abs(p["id_a"]) for p in pts]
            ax.plot(x, y, "o-", ms=3, label=f"Vg = {vg:+.2f} V")
        ax.set_xlabel("Vd [V]")
        ax.set_ylabel("|Id| [A]")

    def _plot_cfet(self, ax, rows, log):
        x = [r["vg_v"] for r in rows]
        plot = ax.semilogy if log else ax.plot
        plot(x, [abs(r["id_n_a"]) for r in rows], "o-", ms=3, label="nFET")
        plot(x, [abs(r["id_p_a"]) for r in rows], "o-", ms=3, label="pFET")
        ax.set_xlabel("Vg [V]")
        ax.set_ylabel("|Id| [A]")

    def _plot_vtc(self, ax, rows, log):
        ax.plot([r["vin_v"] for r in rows], [r["vout_v"] for r in rows],
                "o-", ms=3, label="Vout")
        ax.set_xlabel("Vin [V]")
        ax.set_ylabel("Vout [V]")
