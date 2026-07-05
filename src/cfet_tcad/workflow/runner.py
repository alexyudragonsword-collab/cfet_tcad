"""End-to-end pipeline orchestration (Sentaurus Workbench analog).

geometry -> mesh -> DEVSIM device -> equilibrium -> bias sweeps
         -> CSV / PNG / JSON figures of merit -> VTK for VisIt
"""

from pathlib import Path

from ..extract import extract_dibl, extract_idvg_fom
from ..geometry import BUILDERS
from ..io import (
    plot_idvd,
    plot_idvg,
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

    @property
    def current_scale(self) -> float:
        """2D solutions are per cm of depth and need the effective width;
        3D solutions are true amperes, scaled only by the sheet count."""
        if self.layout.dimension == 2:
            return self.cfg.device.width_cm
        return float(self.cfg.device.n_sheets)

    def setup(self, msh_path: Path) -> None:
        load_mesh(msh_path, self.layout, self.device)
        phys = self.cfg.physics
        setup_equilibrium(
            self.device, self.layout, self.cfg.device,
            oxide_material=phys.oxide_material,
            temperature=phys.temperature,
            taun=phys.taun, taup=phys.taup,
            mobility_model=phys.mobility_model,
            quantum_model=phys.quantum_model,
            dg_gamma_n=phys.dg_gamma_n, dg_gamma_p=phys.dg_gamma_p,
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

    # --- experiments -------------------------------------------------------

    def run_idvg(self) -> dict:
        sim, dev = self.cfg.simulation, self.cfg.device
        scale = self.current_scale
        results = {"curves": [], "fom": {}}
        rows = []

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

    # --- entry point -------------------------------------------------------

    def run(self) -> dict:
        msh = self.build_mesh()
        self.setup(msh)
        if self.cfg.simulation.type == "idvg":
            return self.run_idvg()
        return self.run_idvd()


def run_config(config: RunConfig, output_dir: Path | None = None) -> dict:
    return Runner(config, output_dir).run()
