"""Parameter editor generated from the config dataclasses (the SWB tool
parameter panel analog).

Every field renders as a YAML-fragment line edit (numbers, lists, and
strings parse uniformly through yaml.safe_load); fields with a known
choice set render as combo boxes.  Saving round-trips through
workflow.config.build_config so all dataclass validation applies before
anything reaches disk.
"""

import dataclasses
from pathlib import Path

import yaml
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QLineEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..geometry.params import DeviceParams, MeshParams
from ..physics.mobility import MOBILITY_MODELS
from ..workflow.config import (
    ExtractConfig,
    OutputConfig,
    PhysicsConfig,
    QUANTUM_MODELS,
    SimulationConfig,
    build_config,
)

SECTIONS = (
    ("device", DeviceParams),
    ("mesh", MeshParams),
    ("physics", PhysicsConfig),
    ("simulation", SimulationConfig),
    ("output", OutputConfig),
    ("extract", ExtractConfig),
)

_MATERIAL_CHOICES = ["Silicon", "SiGe15", "SiGe30", "SiGe45"]
CHOICES = {
    ("device", "polarity"): ["n", "p"],
    ("device", "structure"): ["nanosheet_2d", "gaa_3d", "cfet_2d",
                              "cfet_3d", "external"],
    ("device", "channel_material"): _MATERIAL_CHOICES,
    ("device", "channel_material_n"): _MATERIAL_CHOICES,
    ("device", "channel_material_p"): _MATERIAL_CHOICES,
    ("physics", "mobility_model"): list(MOBILITY_MODELS),
    ("physics", "quantum_model"): list(QUANTUM_MODELS),
    ("physics", "oxide_material"): ["SiO2", "HfO2"],
    ("simulation", "type"): ["idvg", "idvd", "cfet_idvg", "cfet_idvd",
                             "cfet_vtc"],
}


def _to_text(value) -> str:
    return yaml.safe_dump(value, default_flow_style=True).strip()


class ConfigForm(QWidget):
    """Editable view of one YAML config, organized by section."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._widgets: dict[tuple, QWidget] = {}
        inner = QWidget()
        vbox = QVBoxLayout(inner)
        for section, cls in SECTIONS:
            box = QGroupBox(section)
            form = QFormLayout(box)
            for f in dataclasses.fields(cls):
                key = (section, f.name)
                if key in CHOICES:
                    w = QComboBox()
                    w.addItems(CHOICES[key])
                    w.setEditable(True)  # allow e.g. SiGe25
                else:
                    w = QLineEdit()
                self._widgets[key] = w
                form.addRow(f.name, w)
            vbox.addWidget(box)
        vbox.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidget(inner)
        scroll.setWidgetResizable(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll)

    # --- data flow ----------------------------------------------------------

    def load(self, path: Path) -> None:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        cfg = build_config(raw)  # validates + fills defaults
        for (section, name), w in self._widgets.items():
            value = getattr(getattr(cfg, section), name)
            text = _to_text(value)
            if isinstance(w, QComboBox):
                w.setCurrentText(str(value))
            else:
                w.setText(text)

    def to_raw(self) -> dict:
        """Collect the form back into a raw config dict (validated)."""
        raw: dict = {}
        for (section, name), w in self._widgets.items():
            text = (w.currentText() if isinstance(w, QComboBox)
                    else w.text()).strip()
            if not text:
                continue
            raw.setdefault(section, {})[name] = yaml.safe_load(text)
        build_config(raw)  # raises ValueError with a precise message
        return raw

    def save(self, path: Path) -> None:
        Path(path).write_text(yaml.safe_dump(self.to_raw(), sort_keys=False),
                              encoding="utf-8")
