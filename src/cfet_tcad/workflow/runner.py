"""End-to-end pipeline orchestration (Sentaurus Workbench analog).

geometry -> mesh -> DEVSIM device -> equilibrium -> bias sweeps
         -> CSV / PNG / JSON figures of merit -> VTK for VisIt
"""

from pathlib import Path

from ..extract import extract_dibl, extract_idvg_fom, extract_vtc_fom
from ..geometry import BUILDERS
from ..io import (
    plot_idvd,
    plot_idvg,
    plot_vtc,
    write_iv_csv,
    write_json,
    write_snapshot,
    write_sweep_collection,
)
from ..meshio_devsim import load_mesh
from ..solve import measure, ramp_biases, setup_equilibrium
from .config import RunConfig


class Runner:
    def __init__(self, config: RunConfig, output_dir: Path | None = None):
        self.cfg = config
        self.out = Path(output_dir or config.output.directory)
        self.out.mkdir(parents=True, exist_ok=True)
        self.device = config.device.name
        self.layout = None
        self._solver = dict(type="dc", absolute_error=1e10,
                            relative_error=1e-10, maximum_iterations=50)
        self._done = 0
        self._total = 0

    # --- pipeline stages -------------------------------------------------

    def build_mesh(self) -> Path:
        msh = self.out / f"{self.device}.msh"
        builder_cls = BUILDERS[self.cfg.device.structure]
        self.layout = builder_cls(self.cfg.device, self.cfg.mesh).build(msh)
        return msh

    @property
    def gates(self) -> list[str]:
        """Gate contacts = contacts attached to insulator regions."""
        return [c for c, r in self.layout.contacts.items()
                if self.layout.regions[r] == "Oxide"]

    def _validate_sim_contacts(self) -> None:
        """A single-device sweep (idvg/idvd) drives contacts literally
        named source/drain/gate; a CFET stack drives source_n/drain_n/
        source_p/drain_p.  Fail early with a clear message instead of a
        cryptic DEVSIM "cannot find parameter drain_bias" mid-solve when
        the wrong simulation type is used on an imported mesh."""
        sim = self.cfg.simulation.type
        have = set(self.layout.contacts)
        if sim in ("idvg", "idvd"):
            needed = ["source", "drain"]
        else:  # cfet_idvg / cfet_vtc
            needed = ["source_n", "drain_n", "source_p", "drain_p"]
        missing = [c for c in needed if c not in have]
        gate_ok = bool(self.gates)
        if missing or not gate_ok:
            hint = ("A CFET stack (source_n/drain_n/source_p/drain_p) "
                    "uses simulation type 'cfet_idvg' or 'cfet_vtc'; a "
                    "single device (source/drain/gate) uses 'idvg' or "
                    "'idvd'.")
            problem = (f"missing contact(s) {missing}" if missing
                       else "no gate contact (on an oxide region)")
            raise ValueError(
                f"simulation type '{sim}' cannot run on this device: "
                f"{problem}. Device contacts are {sorted(have)}. {hint}")

    @property
    def current_scale(self) -> float:
        """2D solutions are per cm of depth and need the effective width;
        3D solutions are true amperes, scaled only by the sheet count."""
        if self.layout.dimension == 2:
            return self.cfg.device.width_cm
        return float(self.cfg.device.n_sheets)

    def setup(self, msh_path: Path) -> None:
        import devsim

        load_mesh(msh_path, self.layout, self.device)
        circuit_contacts = None
        if self.cfg.simulation.type == "cfet_vtc":
            # floating inverter output: both drains tied to circuit node
            # "vout"; the huge resistor to ground creates the node and
            # makes the zero-current equilibrium well-posed
            devsim.circuit_element(name="R1", n1="vout", n2="0",
                                   value=1.0e15)
            circuit_contacts = {"drain_n": "vout", "drain_p": "vout"}
        phys = self.cfg.physics
        setup_equilibrium(
            self.device, self.layout, self.cfg.device,
            oxide_material=phys.oxide_material,
            temperature=phys.temperature,
            taun=phys.taun, taup=phys.taup,
            mobility_model=phys.mobility_model,
            mobility_scale_n=phys.mobility_scale_n,
            mobility_scale_p=phys.mobility_scale_p,
            quantum_model=phys.quantum_model,
            dg_gamma_n=phys.dg_gamma_n, dg_gamma_p=phys.dg_gamma_p,
            circuit_contacts=circuit_contacts,
            solver_args=self._solver,
        )

    # --- sweep helpers ----------------------------------------------------

    def _ramp(self, contacts: list[str], target: float, step: float) -> None:
        ramp_biases(self.device, contacts, target, step=abs(step),
                    min_step=self.cfg.simulation.min_step,
                    solver_args=self._solver)

    def _sweep(self, contacts: list[str], start: float, stop: float,
               step: float, vtk_tag: str | None = None) -> list:
        """Step tied ``contacts`` from ``start`` to ``stop``, measuring all
        terminals at each point and optionally writing VTK snapshots."""
        all_contacts = list(self.layout.contacts.keys())
        ohmic = [c for c, r in self.layout.contacts.items()
                 if self.layout.regions[r] == "Silicon"]
        self._ramp(contacts, start, step)

        n_steps = max(1, round(abs(stop - start) / abs(step)))
        snapshots = []
        points = []
        for i in range(n_steps + 1):
            v = start + (stop - start) * i / n_steps
            if i > 0:
                self._ramp(contacts, v, step)
            points.append(measure(self.device, all_contacts, ohmic))
            self._tick()
            if vtk_tag and self.cfg.output.vtk and (
                    i % self.cfg.output.vtk_stride == 0 or i == n_steps):
                prefix = self.out / "vtk" / f"{vtk_tag}_{i:03d}"
                snapshots.append((v, write_snapshot(prefix)))
        if snapshots:
            write_sweep_collection(self.out / "vtk" / f"{vtk_tag}.pvd",
                                   snapshots)
        return points

    @staticmethod
    def _tag(name: str, value: float) -> str:
        return f"{name}{value:+.3f}".replace("+", "p").replace("-", "m")

    # --- progress reporting (machine-readable, parsed by the GUI) ---------

    def _announce(self, total: int) -> None:
        """Declare the total number of bias points before solving starts.
        flush=True is load-bearing: the GUI reads these lines through a
        pipe, where Python block-buffers stdout by default."""
        self._done, self._total = 0, total
        print(f"@@PROGRESS 0/{total}", flush=True)

    def _tick(self) -> None:
        self._done += 1
        print(f"@@PROGRESS {self._done}/{self._total}", flush=True)

    # --- experiments -------------------------------------------------------

    def run_idvg(self) -> dict:
        sim, dev = self.cfg.simulation, self.cfg.device
        scale = self.current_scale
        results = {"curves": [], "fom": {}}
        rows = []
        pts = max(1, round(abs(sim.vg_stop - sim.vg_start)
                           / abs(sim.vg_step))) + 1
        self._announce(len(sim.vd) * pts)

        for vd in sim.vd:
            self._ramp(self.gates, sim.vg_start, sim.vg_step)
            self._ramp(["drain"], vd, sim.vd_step)

            points = self._sweep(self.gates, sim.vg_start,
                                 sim.vg_stop, sim.vg_step,
                                 vtk_tag=self._tag("idvg_vd", vd))

            vg = [p.biases[self.gates[0]] for p in points]
            id_a = [p.currents["drain"] * scale for p in points]
            label = f"Vd = {vd:+.2f} V"
            results["curves"].append(
                {"vg": vg, "id": id_a, "vd": vd, "label": label})
            rows += [{"vg_v": g, "vd_v": vd, "id_a": i,
                      "is_a": p.currents["source"] * scale}
                     for g, i, p in zip(vg, id_a, points)]

            results["fom"][label] = extract_idvg_fom(
                vg, id_a, polarity=dev.polarity,
                icrit=self.cfg.extract.icrit_a)

        if len(sim.vd) >= 2:
            vds = sorted(sim.vd, key=abs)
            results["fom"]["dibl_mv_per_v"] = extract_dibl(
                results["fom"][f"Vd = {vds[0]:+.2f} V"],
                results["fom"][f"Vd = {vds[-1]:+.2f} V"],
                vds[0], vds[-1])

        write_iv_csv(self.out / "idvg.csv", rows)
        plot_idvg(self.out / "idvg.png", results["curves"],
                  title=f"{self.device} Id-Vg ({self._width_label()})")
        write_json(self.out / "fom.json", results["fom"])
        return results

    def run_idvd(self) -> dict:
        sim, dev = self.cfg.simulation, self.cfg.device
        scale = self.current_scale
        results = {"curves": []}
        rows = []
        pts = max(1, round(abs(sim.vd_stop - sim.vd_start)
                           / abs(sim.vd_step))) + 1
        self._announce(len(sim.vg) * pts)

        for vg in sim.vg:
            self._ramp(["drain"], sim.vd_start, sim.vd_step)
            self._ramp(self.gates, vg, sim.vg_step)

            points = self._sweep(["drain"], sim.vd_start, sim.vd_stop,
                                 sim.vd_step,
                                 vtk_tag=self._tag("idvd_vg", vg))
            vd = [p.biases["drain"] for p in points]
            id_a = [p.currents["drain"] * scale for p in points]
            label = f"Vg = {vg:+.2f} V"
            results["curves"].append(
                {"vd": vd, "id": id_a, "vg": vg, "label": label})
            rows += [{"vg_v": vg, "vd_v": d, "id_a": i,
                      "is_a": p.currents["source"] * scale}
                     for d, i, p in zip(vd, id_a, points)]

        write_iv_csv(self.out / "idvd.csv", rows)
        plot_idvd(self.out / "idvd.png", results["curves"],
                  title=f"{self.device} Id-Vd ({self._width_label()})")
        return results

    def _width_label(self) -> str:
        dev = self.cfg.device
        if self.layout.dimension == 2:
            return f"W_eff = {dev.width_cm*1e4:.3f} um"
        return (f"3D GAA {dev.sheet_width_nm:.0f}x{dev.t_si_nm:.0f} nm, "
                f"{dev.n_sheets} sheet(s)")

    def run_cfet_idvg(self) -> dict:
        """Common-gate transfer sweep of the CFET stack, biased like a CMOS
        pair: nFET source grounded / drain at vdd, pFET source at vdd /
        drain grounded.  One sweep yields both devices' transfer curves
        from a single coupled solve (pFET Vgs = Vg - vdd)."""
        sim = self.cfg.simulation
        vdd = sim.vdd
        scale = self.current_scale
        results = {"curves": [], "fom": {}}

        self._announce(max(1, round(abs(sim.vg_stop - sim.vg_start)
                                    / abs(sim.vg_step))) + 1)
        self._ramp(["source_p"], vdd, sim.vd_step)
        self._ramp(["drain_n"], vdd, sim.vd_step)
        points = self._sweep(self.gates, sim.vg_start, sim.vg_stop,
                             sim.vg_step, vtk_tag="cfet_idvg")

        vg = [p.biases[self.gates[0]] for p in points]
        id_n = [p.currents["drain_n"] * scale for p in points]
        id_p = [p.currents["drain_p"] * scale for p in points]
        results["curves"] = [
            {"vg": vg, "id": id_n, "label": "nFET (top)"},
            {"vg": vg, "id": id_p, "label": "pFET (bottom)"},
        ]
        results["fom"]["nFET"] = extract_idvg_fom(
            vg, id_n, polarity="n", icrit=self.cfg.extract.icrit_a)
        results["fom"]["pFET"] = extract_idvg_fom(
            [v - vdd for v in vg], id_p, polarity="p",
            icrit=self.cfg.extract.icrit_a)

        rows = [{"vg_v": g, "id_n_a": a, "id_p_a": b,
                 "is_n_a": p.currents["source_n"] * scale,
                 "is_p_a": p.currents["source_p"] * scale}
                for g, a, b, p in zip(vg, id_n, id_p, points)]
        write_iv_csv(self.out / "cfet_idvg.csv", rows)
        plot_idvg(self.out / "cfet_idvg.png", results["curves"],
                  title=(f"{self.device} CFET stack common-gate sweep "
                         f"(Vdd = {vdd} V, {self._width_label()})"))
        write_json(self.out / "fom.json", results["fom"])
        return results

    def run_cfet_vtc(self) -> dict:
        """Inverter voltage transfer characteristic of the CFET stack.

        Vout is the floating node shared by both drains, solved
        self-consistently by the mixed device/circuit Newton system; the
        input sweeps the common gate.  Also records the supply current
        through the pFET source (short-circuit current bell curve).
        """
        import devsim

        from ..solve.sweep import contact_current

        sim = self.cfg.simulation
        vdd = sim.vdd
        scale = self.current_scale

        self._ramp(["source_p"], vdd, sim.vd_step)

        n_steps = max(1, round(abs(sim.vg_stop - sim.vg_start)
                               / abs(sim.vg_step)))
        self._announce(n_steps + 1)
        vin, vout, i_dd = [], [], []
        snapshots = []
        for i in range(n_steps + 1):
            v = sim.vg_start + (sim.vg_stop - sim.vg_start) * i / n_steps
            if i > 0:
                self._ramp(self.gates, v, sim.vg_step)
            vin.append(v)
            vout.append(devsim.get_circuit_node_value(node="vout"))
            i_dd.append(contact_current(self.device, "source_p") * scale)
            self._tick()
            if self.cfg.output.vtk and (
                    i % self.cfg.output.vtk_stride == 0 or i == n_steps):
                prefix = self.out / "vtk" / f"vtc_{i:03d}"
                snapshots.append((v, write_snapshot(prefix)))
        if snapshots:
            write_sweep_collection(self.out / "vtk" / "vtc.pvd", snapshots)

        fom = extract_vtc_fom(vin, vout, vdd)
        rows = [{"vin_v": a, "vout_v": b, "i_dd_a": c}
                for a, b, c in zip(vin, vout, i_dd)]
        write_iv_csv(self.out / "vtc.csv", rows)
        plot_vtc(self.out / "vtc.png", vin, vout, i_dd,
                 title=f"{self.device} CFET inverter VTC (Vdd = {vdd} V)")
        write_json(self.out / "fom.json", fom)
        return {"vin": vin, "vout": vout, "i_dd": i_dd, "fom": fom}

    # --- entry point -------------------------------------------------------

    def run(self) -> dict:
        msh = self.build_mesh()
        self._validate_sim_contacts()  # clear error before any DEVSIM work
        self.setup(msh)
        if self.cfg.simulation.type == "idvg":
            return self.run_idvg()
        if self.cfg.simulation.type == "cfet_idvg":
            return self.run_cfet_idvg()
        if self.cfg.simulation.type == "cfet_vtc":
            return self.run_cfet_vtc()
        return self.run_idvd()


def run_config(config: RunConfig, output_dir: Path | None = None) -> dict:
    return Runner(config, output_dir).run()
