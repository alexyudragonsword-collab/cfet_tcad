"""Mesh generation: file format, physical groups, parameter validation."""

import pytest

from cfet_tcad.geometry import DeviceParams, MeshParams, Nanosheet2DBuilder
from cfet_tcad.geometry.params import (
    CONTACT_DRAIN,
    CONTACT_GATE_BOTTOM,
    CONTACT_GATE_TOP,
    CONTACT_SOURCE,
    INTERFACE_SI_OX_BOTTOM,
    INTERFACE_SI_OX_TOP,
    REGION_OXIDE_BOTTOM,
    REGION_OXIDE_TOP,
    REGION_SILICON,
)

ALL_GROUPS = [
    REGION_SILICON, REGION_OXIDE_TOP, REGION_OXIDE_BOTTOM,
    CONTACT_SOURCE, CONTACT_DRAIN, CONTACT_GATE_TOP, CONTACT_GATE_BOTTOM,
    INTERFACE_SI_OX_TOP, INTERFACE_SI_OX_BOTTOM,
]


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    msh = tmp_path_factory.mktemp("mesh") / "dev.msh"
    layout = Nanosheet2DBuilder(DeviceParams(), MeshParams()).build(msh)
    return msh, layout


def test_msh_is_version_2_2_ascii(built):
    msh, _ = built
    text = msh.read_text()
    assert text.startswith("$MeshFormat\n2.2 0 8")


def test_all_physical_groups_present(built):
    msh, _ = built
    text = msh.read_text()
    for name in ALL_GROUPS:
        assert f'"{name}"' in text, f"missing physical group {name}"


def test_layout_contract(built):
    _, layout = built
    assert layout.dimension == 2
    assert layout.regions[REGION_SILICON] == "Silicon"
    assert layout.regions[REGION_OXIDE_TOP] == "Oxide"
    assert layout.contacts[CONTACT_GATE_TOP] == REGION_OXIDE_TOP
    assert layout.contacts[CONTACT_SOURCE] == REGION_SILICON
    assert layout.interfaces[INTERFACE_SI_OX_TOP] == (
        REGION_SILICON, REGION_OXIDE_TOP)


def test_invalid_params_rejected():
    with pytest.raises(ValueError):
        DeviceParams(polarity="x")
    with pytest.raises(ValueError):
        DeviceParams(t_si_nm=-1)
    with pytest.raises(ValueError):
        MeshParams(ny_si=1)
