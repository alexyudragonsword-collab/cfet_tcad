"""FOM extraction on synthetic transfer curves with known properties."""

import numpy as np
import pytest

from cfet_tcad.extract import (
    dibl,
    extract_idvg_fom,
    subthreshold_swing,
    vt_constant_current,
    vt_max_gm,
)


def synthetic_idvg(vt=0.3, ss_mv=70.0, ion_scale=1e-5, vg=None):
    """Exponential below vt, linear above; smooth crossover."""
    vg = np.arange(0.0, 0.701, 0.025) if vg is None else vg
    i_sub = 1e-8 * 10 ** ((vg - vt) / (ss_mv / 1000.0))
    i_on = ion_scale * np.maximum(vg - vt, 0.0)
    return vg, i_sub / (1 + i_sub / 1e-7) + i_on


def test_vt_constant_current_recovers_vt():
    vg, idr = synthetic_idvg(vt=0.3)
    # by construction Id(vt) = 1e-8
    assert vt_constant_current(vg, idr, icrit=1e-8) == pytest.approx(0.3,
                                                                     abs=0.01)


def test_subthreshold_swing_recovers_ss():
    vg, idr = synthetic_idvg(vt=0.35, ss_mv=65.0)
    ss = subthreshold_swing(vg, idr, icrit=1e-9)
    assert ss == pytest.approx(65.0, rel=0.05)


def test_vt_max_gm_near_linear_onset():
    vg, idr = synthetic_idvg(vt=0.3)
    vt = vt_max_gm(vg, idr)
    assert 0.25 < vt < 0.40


def test_dibl_sign_and_magnitude():
    assert dibl(0.30, 0.24, 0.05, 0.70) == pytest.approx(92.3, rel=0.01)


def test_extract_fom_nfet():
    vg, idr = synthetic_idvg(vt=0.3)
    fom = extract_idvg_fom(vg, idr, polarity="n", icrit=1e-8)
    assert fom["vt_constant_current_v"] == pytest.approx(0.3, abs=0.01)
    assert fom["ion_a"] > 100 * fom["ioff_a"]
    assert fom["ion_ioff_ratio"] > 100


def test_extract_fom_pfet_signs():
    vg, idr = synthetic_idvg(vt=0.3)
    # mirror to pFET: negative gate voltages, negative current
    fom = extract_idvg_fom(-vg, -idr, polarity="p", icrit=1e-8)
    assert fom["vt_constant_current_v"] == pytest.approx(-0.3, abs=0.01)
    assert fom["vdd_v"] == pytest.approx(-0.7)
    assert fom["ion_a"] > 0


def test_insufficient_data_gives_nan():
    assert np.isnan(vt_constant_current([0, 0.1], [1e-3, 1e-2], icrit=1e-9))
    assert np.isnan(subthreshold_swing([0.0, 0.1], [1e-3, 1e-2], icrit=1e-9))
