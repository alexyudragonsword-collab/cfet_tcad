"""Bias ramping and IV sweep drivers with adaptive step control."""

from dataclasses import dataclass, field

import devsim

from .initial import DEFAULT_SOLVER_ARGS
from ..physics.equations import ECE_NAME, HCE_NAME, contact_bias_name


class ConvergenceError(RuntimeError):
    pass


@dataclass
class BiasPoint:
    """Contact biases and terminal currents (2D currents are A/cm depth)."""
    biases: dict
    currents: dict
    fields: dict = field(default_factory=dict)


def contact_current(device: str, contact: str) -> float:
    return (devsim.get_contact_current(device=device, contact=contact,
                                       equation=ECE_NAME)
            + devsim.get_contact_current(device=device, contact=contact,
                                         equation=HCE_NAME))


def set_bias(device: str, contact: str, value: float) -> None:
    devsim.set_parameter(device=device, name=contact_bias_name(contact),
                         value=value)


def get_bias(device: str, contact: str) -> float:
    return devsim.get_parameter(device=device,
                                name=contact_bias_name(contact))


def ramp_biases(device: str, contacts: list[str], target: float,
                step: float = 0.05, min_step: float = 1e-4,
                solver_args: dict | None = None) -> None:
    """Ramp one or more tied contacts to ``target``, halving the step on
    convergence failure."""
    solver_args = solver_args or DEFAULT_SOLVER_ARGS
    step = abs(step)
    while True:
        start = get_bias(device, contacts[0])
        remaining = target - start
        if remaining == 0.0:
            return
        delta = max(-step, min(step, remaining))
        for c in contacts:
            set_bias(device, c, start + delta)
        try:
            devsim.solve(**solver_args)
        except devsim.error:
            for c in contacts:
                set_bias(device, c, start)
            step /= 2.0
            if step < min_step:
                raise ConvergenceError(
                    f"bias ramp on {contacts} failed near {start:+.4f} V "
                    f"(step underflow below {min_step} V)") from None


def ramp_bias(device: str, contact: str, target: float,
              step: float = 0.05, min_step: float = 1e-4,
              solver_args: dict | None = None) -> None:
    """Ramp a single contact bias to ``target``."""
    ramp_biases(device, [contact], target, step=step, min_step=min_step,
                solver_args=solver_args)


def measure(device: str, contacts: list[str],
            current_contacts: list[str] | None = None) -> BiasPoint:
    """Record biases on ``contacts`` and currents on ``current_contacts``
    (defaults to all ``contacts``; gate contacts on insulators carry no
    continuity equation and must be excluded from current measurement)."""
    if current_contacts is None:
        current_contacts = contacts
    return BiasPoint(
        biases={c: get_bias(device, c) for c in contacts},
        currents={c: contact_current(device, c) for c in current_contacts},
    )
