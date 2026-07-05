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
