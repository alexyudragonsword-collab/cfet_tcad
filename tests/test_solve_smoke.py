"""Coarse-mesh equilibrium smoke test: full physics assembly must converge
and produce a physically sensible potential."""

import pytest

from cfet_tcad.geometry import DeviceParams, MeshParams, Nanosheet2DBuilder
from cfet_tcad.meshio_devsim import load_mesh
from cfet_tcad.solve import setup_equilibrium


@pytest.mark.parametrize("polarity,wf", [("n", 4.50), ("p", 4.72)])
def test_equilibrium_converges(tmp_path, fresh_devsim, polarity, wf):
    devsim = fresh_devsim
    params = DeviceParams(name=f"smoke_{polarity}", polarity=polarity,
                          gate_workfunction_ev=wf)
    mesh = MeshParams(nx_sd=8, nx_gate=12, ny_si=6, ny_ox=2)
    msh = tmp_path / "dev.msh"
    layout = Nanosheet2DBuilder(params, mesh).build(msh)
    device = load_mesh(msh, layout, params.name)

    setup_equilibrium(device, layout, params)  # raises on non-convergence

    pot = devsim.get_node_model_values(device=device, region="silicon",
                                       name="Potential")
    # equilibrium potential referenced to intrinsic level must stay within
    # the built-in range of a 1e20-doped junction (~ +/- 0.6 V)
    assert -0.7 < min(pot) < max(pot) < 0.7
    majority = "Electrons" if polarity == "n" else "Holes"
    carriers = devsim.get_node_model_values(device=device, region="silicon",
                                            name=majority)
    assert max(carriers) > 1e19  # S/D extensions are degenerate
    assert min(carriers) > 0.0


@pytest.mark.slow
def test_progress_lines_cover_all_bias_points(tmp_path, capsys, fresh_devsim):
    """The runner announces '@@PROGRESS k/total' per measured point (the
    GUI's progress source): the final line must reach total."""
    import re

    from cfet_tcad.workflow.config import build_config
    from cfet_tcad.workflow.runner import run_config

    cfg = build_config({
        "device": {"name": "prog", "polarity": "n",
                   "gate_workfunction_ev": 4.5},
        "mesh": {"nx_sd": 6, "nx_gate": 10, "ny_si": 5, "ny_ox": 2},
        "simulation": {"type": "idvg", "vd": [0.7], "vg_start": 0.0,
                       "vg_stop": 0.2, "vg_step": 0.1},
        "output": {"directory": "unused", "vtk": False},
    })
    run_config(cfg, tmp_path)
    ticks = re.findall(r"^@@PROGRESS (\d+)/(\d+)$",
                       capsys.readouterr().out, re.M)
    assert ticks[0] == ("0", "3")     # 3 points: vg = 0.0, 0.1, 0.2
    assert ticks[-1] == ("3", "3")    # ends complete
    assert len(ticks) == 4            # announce + one per point
