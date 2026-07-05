"""Analytic doping profiles registered as DEVSIM node models.

The single-silicon-region device uses a lateral profile: heavily doped S/D
extensions with gaussian tails decaying into a lightly counter-doped
channel.  Junctions are placed at the gate edges.
"""

import devsim
from devsim.python_packages.model_create import CreateNodeModel

from ..geometry.params import DeviceParams


def _sd_profile(x1: float, x2: float, lam: float) -> str:
    """S/D doping profile normalized to 1 in the extensions.

    Flat at 1 outside [x1, x2], gaussian tails (decay length ``lam``)
    inside the channel from each junction.
    """
    # NB: DEVSIM's parser binds unary minus tighter than '^' (-a^2 == (+a)^2),
    # so the exponent must be parenthesized as a whole
    left = f"ifelse(x < {x1}, 1, exp(-(((x - {x1})/{lam})^2)))"
    right = f"ifelse(x > {x2}, 1, exp(-((({x2} - x)/{lam})^2)))"
    return f"({left} + {right})"


def create_doping(device: str, region: str, params: DeviceParams) -> None:
    """Create Donors, Acceptors, and NetDoping node models on ``region``."""
    x1 = params.l_sd
    x2 = params.l_sd + params.l_gate
    profile = _sd_profile(x1, x2, params.junction_lambda)
    sd = params.sd_doping_cm3
    ch = params.channel_doping_cm3

    if params.polarity == "n":
        donors = f"{sd} * {profile}"
        acceptors = f"{ch}"
    else:
        donors = f"{ch}"
        acceptors = f"{sd} * {profile}"

    CreateNodeModel(device, region, "Donors", donors)
    CreateNodeModel(device, region, "Acceptors", acceptors)
    CreateNodeModel(device, region, "NetDoping", "Donors - Acceptors")
    CreateNodeModel(device, region, "TotalDoping", "Donors + Acceptors")
    devsim.edge_from_node_model(device=device, region=region,
                                node_model="NetDoping")
