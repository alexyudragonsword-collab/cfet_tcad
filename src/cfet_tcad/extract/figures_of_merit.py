"""Figure-of-merit extraction from Id-Vg data (Sentaurus Inspect analog).

All functions take plain numpy arrays.  For pFETs pass overdrive-normalized
data: vg -> -vg and id -> |id| so the transfer curve is monotonically
increasing; :func:`extract_idvg_fom` handles this via ``polarity``.
"""

import numpy as np


def _monotone(vg, id_abs):
    vg = np.asarray(vg, dtype=float)
    id_abs = np.abs(np.asarray(id_abs, dtype=float))
    order = np.argsort(vg)
    return vg[order], id_abs[order]


def vt_constant_current(vg, id_abs, icrit: float) -> float:
    """Gate voltage where the current crosses ``icrit`` (log interpolation)."""
    vg, id_abs = _monotone(vg, id_abs)
    logi = np.log10(np.maximum(id_abs, 1e-30))
    logc = np.log10(icrit)
    above = np.nonzero(logi >= logc)[0]
    if len(above) == 0 or above[0] == 0:
        return float("nan")
    j = above[0]
    x0, x1 = logi[j - 1], logi[j]
    return float(vg[j - 1] + (logc - x0) * (vg[j] - vg[j - 1]) / (x1 - x0))


def vt_max_gm(vg, id_abs) -> float:
    """Linear extrapolation of Id at the maximum-transconductance point."""
    vg, id_abs = _monotone(vg, id_abs)
    if len(vg) < 3:
        return float("nan")
    gm = np.gradient(id_abs, vg)
    j = int(np.argmax(gm))
    if gm[j] <= 0:
        return float("nan")
    return float(vg[j] - id_abs[j] / gm[j])


def subthreshold_swing(vg, id_abs, icrit: float = 1e-8) -> float:
    """Steepest swing dVg/dlog10(Id) [mV/dec] in the subthreshold region.

    Uses the minimum pairwise slope over points below ``icrit``, which is
    robust to sweeps that start near the off-state (few subthreshold
    points) and to the turnover into the linear region."""
    vg, id_abs = _monotone(vg, id_abs)
    mask = (id_abs > 0) & (id_abs < icrit)
    if mask.sum() < 2:
        return float("nan")
    v, logi = vg[mask], np.log10(id_abs[mask])
    dlog = np.diff(logi)
    valid = dlog > 1e-6  # increasing current only
    if not valid.any():
        return float("nan")
    slopes = np.diff(v)[valid] / dlog[valid]
    return float(np.min(slopes) * 1000.0)


def dibl(vt_lin: float, vt_sat: float, vd_lin: float, vd_sat: float) -> float:
    """DIBL [mV/V] from constant-current Vt at low and high drain bias."""
    dv = abs(vd_sat - vd_lin)
    if dv == 0:
        return float("nan")
    return float((vt_lin - vt_sat) / dv * 1000.0)


def extract_idvg_fom(vg, id_signed, polarity: str = "n",
                     icrit: float = 1e-8, vdd: float | None = None) -> dict:
    """Extract Vt/SS/Ion/Ioff from one Id-Vg sweep.

    ``icrit`` is the constant-current criterion in A (already scaled to the
    device width).  ``vdd`` defaults to the largest |Vg| in the sweep.
    Returned voltages are in the device's native sign convention
    (negative Vt for pFET).
    """
    vg = np.asarray(vg, dtype=float)
    id_abs = np.abs(np.asarray(id_signed, dtype=float))
    sign = 1.0 if polarity == "n" else -1.0
    v = sign * vg  # overdrive axis, increasing = more on

    vdd = vdd if vdd is not None else float(np.max(v))
    ion = float(id_abs[np.argmax(v)])
    ioff_idx = int(np.argmin(np.abs(v)))
    ioff = float(id_abs[ioff_idx])

    vt_cc = vt_constant_current(v, id_abs, icrit)
    vt_gm = vt_max_gm(v, id_abs)
    ss = subthreshold_swing(v, id_abs, icrit=icrit)

    return {
        "polarity": polarity,
        "vt_constant_current_v": sign * vt_cc,
        "vt_max_gm_v": sign * vt_gm,
        "ss_mv_per_dec": ss,
        "ion_a": ion,
        "ioff_a": ioff,
        "ion_ioff_ratio": ion / ioff if ioff > 0 else float("inf"),
        "icrit_a": icrit,
        "vdd_v": sign * vdd,
    }


def extract_dibl(fom_lin: dict, fom_sat: dict,
                 vd_lin: float, vd_sat: float) -> float:
    """DIBL from the FOM dicts of a linear- and a saturation-Vd sweep."""
    sign = 1.0 if fom_lin["polarity"] == "n" else -1.0
    return dibl(sign * fom_lin["vt_constant_current_v"],
                sign * fom_sat["vt_constant_current_v"],
                abs(vd_lin), abs(vd_sat))


def extract_vtc_fom(vin, vout, vdd: float) -> dict:
    """Inverter VTC figures of merit.

    VM: switching threshold (vout == vin crossing); gain: max |dVout/dVin|;
    VIL/VIH: unity-gain input voltages; noise margins NML = VIL - VOL,
    NMH = VOH - VIH with VOL/VOH read at the sweep ends.
    """
    vin = np.asarray(vin, dtype=float)
    vout = np.asarray(vout, dtype=float)
    order = np.argsort(vin)
    vin, vout = vin[order], vout[order]

    # switching threshold: vout - vin crosses zero
    diff = vout - vin
    vm = float("nan")
    cross = np.nonzero(np.diff(np.sign(diff)))[0]
    if len(cross):
        j = cross[0]
        vm = float(vin[j] + diff[j] * (vin[j + 1] - vin[j])
                   / (diff[j] - diff[j + 1]))

    gain = -np.gradient(vout, vin)  # inverting: positive numbers
    max_gain = float(np.max(gain))

    # unity-gain points bracket the transition region
    above = np.nonzero(gain >= 1.0)[0]
    vil = float(vin[above[0]]) if len(above) else float("nan")
    vih = float(vin[above[-1]]) if len(above) else float("nan")

    voh = float(vout[0])
    vol = float(vout[-1])
    return {
        "vm_v": vm,
        "max_gain": max_gain,
        "vil_v": vil,
        "vih_v": vih,
        "voh_v": voh,
        "vol_v": vol,
        "nml_v": vil - vol,
        "nmh_v": voh - vih,
        "vdd_v": vdd,
    }
