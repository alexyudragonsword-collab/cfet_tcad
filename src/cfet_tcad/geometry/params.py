"""Device and mesh parameter definitions.

All geometric quantities are stored in centimeters internally (DEVSIM's
native unit system); constructors accept nanometers for convenience.
"""

from dataclasses import dataclass

NM_TO_CM = 1.0e-7

#: doping profile kinds accepted in an external-mesh doping spec
DOPING_PROFILES = ("lateral_sd", "uniform", "expression")


@dataclass
class DeviceParams:
    """Parametric description of a single nanosheet channel.

    The 2D builder realizes this as a double-gate along-channel cross
    section (x = transport direction, y = confinement direction), which is
    the standard 2D approximation of a gate-all-around nanosheet.
    """

    name: str = "nanosheet"
    polarity: str = "n"  # "n" (CFET top device) or "p" (CFET bottom device)
    # "nanosheet_2d" | "gaa_3d" | "cfet_2d" | "cfet_3d" | "external"
    structure: str = "nanosheet_2d"

    # structure == "external": user-supplied gmsh MSH 2.2 mesh plus the
    # physical-group mapping the DEVSIM loader needs (see
    # geometry.external.ExternalMeshBuilder for the schema)
    external: dict | None = None

    # geometry [nm]
    l_gate_nm: float = 15.0
    t_si_nm: float = 5.0
    t_ox_nm: float = 1.0
    l_sd_nm: float = 15.0
    junction_lambda_nm: float = 1.5  # gaussian decay length of S/D doping tail

    # doping [cm^-3]
    sd_doping_cm3: float = 1.0e20
    channel_doping_cm3: float = 1.0e15  # opposite type to S/D

    # gate stack
    gate_workfunction_ev: float = 4.40  # ~n-type WF; use ~4.82 for pFET

    # channel semiconductor (MATERIALS key): single-sheet structures
    channel_material: str = "Silicon"

    # CFET stack (structure == "cfet_2d"/"cfet_3d"): per-device gate
    # metals, per-sheet channel materials (e.g. SiGe30 pFET), and the
    # unmeshed spacer between the stacked sheets (occupied by gate metal)
    gate_workfunction_n_ev: float = 4.50
    gate_workfunction_p_ev: float = 4.72
    channel_material_n: str = "Silicon"
    channel_material_p: str = "Silicon"
    t_gap_nm: float = 10.0

    # current scaling: effective width = sheet width x number of sheets
    # (an ideal parallel multiplier - no extra geometry is meshed)
    sheet_width_nm: float = 20.0
    n_sheets: int = 1

    # geometric channel replication per device (cfet_3d only): real
    # meshed copies, unlike the n_sheets multiplier above.  n_fins
    # places copies side by side along z (paper-style fin arrays,
    # center-to-center fin_pitch); n_stacked_sheets stacks copies
    # vertically within each device (multi-nanosheet stacks,
    # center-to-center sheet_pitch)
    n_fins: int = 1
    fin_pitch_nm: float = 26.0
    n_stacked_sheets: int = 1
    sheet_pitch_nm: float = 15.0

    def __post_init__(self):
        if self.polarity not in ("n", "p"):
            raise ValueError(f"polarity must be 'n' or 'p', got {self.polarity!r}")
        valid = ("nanosheet_2d", "gaa_3d", "cfet_2d", "cfet_3d", "external")
        if self.structure not in valid:
            raise ValueError(
                f"structure must be one of {valid}, got {self.structure!r}")
        for attr in ("l_gate_nm", "t_si_nm", "t_ox_nm", "l_sd_nm",
                     "junction_lambda_nm", "sd_doping_cm3", "channel_doping_cm3",
                     "sheet_width_nm"):
            if getattr(self, attr) <= 0:
                raise ValueError(f"{attr} must be positive")
        self._validate_replication()
        self._validate_external()

    def _validate_replication(self) -> None:
        if self.n_fins < 1 or self.n_stacked_sheets < 1:
            raise ValueError("n_fins and n_stacked_sheets must be >= 1")
        if (self.n_fins > 1 or self.n_stacked_sheets > 1) \
                and self.structure != "cfet_3d":
            raise ValueError(
                "geometric channel replication (n_fins/n_stacked_sheets"
                " > 1) is only implemented for structure: cfet_3d")
        if self.n_fins > 1 and \
                self.fin_pitch_nm < self.sheet_width_nm + 2 * self.t_ox_nm:
            raise ValueError(
                f"fin_pitch_nm ({self.fin_pitch_nm}) must be >= "
                f"sheet_width_nm + 2*t_ox_nm "
                f"({self.sheet_width_nm + 2 * self.t_ox_nm}) or the "
                f"oxide shells overlap")
        if self.n_stacked_sheets > 1 and \
                self.sheet_pitch_nm < self.t_si_nm + 2 * self.t_ox_nm:
            raise ValueError(
                f"sheet_pitch_nm ({self.sheet_pitch_nm}) must be >= "
                f"t_si_nm + 2*t_ox_nm "
                f"({self.t_si_nm + 2 * self.t_ox_nm}) or the oxide "
                f"shells overlap")

    def _validate_external(self) -> None:
        if self.structure != "external":
            if self.external is not None:
                raise ValueError("device.external is only valid with "
                                 "structure: external")
            return
        ext = self.external
        if not isinstance(ext, dict):
            raise ValueError("structure: external requires a device.external "
                             "mapping (mesh_file, dimension, regions, "
                             "contacts, ...)")
        for key in ("mesh_file", "dimension", "regions", "contacts"):
            if not ext.get(key):
                raise ValueError(f"device.external.{key} is required")
        if int(ext["dimension"]) not in (2, 3):
            raise ValueError("device.external.dimension must be 2 or 3")
        for region, material in ext["regions"].items():
            if material not in ("Silicon", "Oxide"):
                raise ValueError(
                    f"device.external.regions[{region!r}] must be 'Silicon' "
                    f"or 'Oxide' (DEVSIM material), got {material!r}")
        for contact, region in ext["contacts"].items():
            if region not in ext["regions"]:
                raise ValueError(
                    f"device.external.contacts[{contact!r}] references "
                    f"unknown region {region!r}")
        for name, pair in (ext.get("interfaces") or {}).items():
            if (not isinstance(pair, (list, tuple)) or len(pair) != 2
                    or any(r not in ext["regions"] for r in pair)):
                raise ValueError(
                    f"device.external.interfaces[{name!r}] must be a pair "
                    f"of declared regions, got {pair!r}")
        for region, spec in (ext.get("doping") or {}).items():
            if region not in ext["regions"]:
                raise ValueError(
                    f"device.external.doping[{region!r}] references an "
                    f"undeclared region")
            profile = (spec or {}).get("profile", "lateral_sd")
            if profile not in DOPING_PROFILES:
                raise ValueError(
                    f"device.external.doping[{region!r}].profile must be "
                    f"one of {DOPING_PROFILES}, got {profile!r}")
            if profile == "expression" and not (
                    spec.get("donors") and spec.get("acceptors")):
                raise ValueError(
                    f"device.external.doping[{region!r}]: expression "
                    f"profile needs 'donors' and 'acceptors'")

    # --- derived quantities in cm ---
    @property
    def l_gate(self) -> float:
        return self.l_gate_nm * NM_TO_CM

    @property
    def t_si(self) -> float:
        return self.t_si_nm * NM_TO_CM

    @property
    def t_ox(self) -> float:
        return self.t_ox_nm * NM_TO_CM

    @property
    def l_sd(self) -> float:
        return self.l_sd_nm * NM_TO_CM

    @property
    def junction_lambda(self) -> float:
        return self.junction_lambda_nm * NM_TO_CM

    @property
    def l_total(self) -> float:
        return 2.0 * self.l_sd + self.l_gate

    @property
    def fin_pitch(self) -> float:
        return self.fin_pitch_nm * NM_TO_CM

    @property
    def sheet_pitch(self) -> float:
        return self.sheet_pitch_nm * NM_TO_CM

    @property
    def width_cm(self) -> float:
        """Effective device width used to scale 2D (A/cm) currents to A."""
        return self.sheet_width_nm * NM_TO_CM * self.n_sheets


@dataclass
class MeshParams:
    """Structured (transfinite) mesh densities: element counts per block."""

    nx_sd: int = 24     # x divisions in each source/drain extension column
    nx_gate: int = 40   # x divisions under the gate
    ny_si: int = 12     # y divisions across the silicon body
    ny_ox: int = 4      # y divisions across each oxide layer
    nz_w: int = 8       # z divisions across the sheet width (3D only)
    si_bump: float = 0.65  # <1 concentrates silicon y-nodes at the interfaces

    def __post_init__(self):
        for attr in ("nx_sd", "nx_gate", "ny_si", "ny_ox", "nz_w"):
            if getattr(self, attr) < 2:
                raise ValueError(f"{attr} must be >= 2")


# Physical group naming contract shared by geometry builders and the
# DEVSIM mesh loader (see cfet_tcad.meshio_devsim.loader).
REGION_SILICON = "silicon"
REGION_OXIDE_TOP = "oxide_top"
REGION_OXIDE_BOTTOM = "oxide_bottom"
REGION_OXIDE = "oxide"            # 3D GAA: single wrap-around shell
CONTACT_SOURCE = "source"
CONTACT_DRAIN = "drain"
CONTACT_GATE_TOP = "gate_top"
CONTACT_GATE_BOTTOM = "gate_bottom"
CONTACT_GATE = "gate"             # 3D GAA: single all-around gate
INTERFACE_SI_OX_TOP = "si_ox_top"
INTERFACE_SI_OX_BOTTOM = "si_ox_bottom"
INTERFACE_SI_OX = "si_ox"         # 3D GAA

SILICON_REGIONS = (REGION_SILICON,)
OXIDE_REGIONS = (REGION_OXIDE_TOP, REGION_OXIDE_BOTTOM, REGION_OXIDE)
GATE_CONTACTS = (CONTACT_GATE_TOP, CONTACT_GATE_BOTTOM, CONTACT_GATE)
OHMIC_CONTACTS = (CONTACT_SOURCE, CONTACT_DRAIN)
INTERFACES = (INTERFACE_SI_OX_TOP, INTERFACE_SI_OX_BOTTOM, INTERFACE_SI_OX)
