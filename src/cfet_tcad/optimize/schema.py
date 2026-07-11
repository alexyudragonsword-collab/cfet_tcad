"""Hand-maintained bounds for the parameters an LLM optimizer may tune.

The dataclass validation in ``geometry.params``/``workflow.config`` is
imperative (``if x <= 0: raise ...``), so there is no declarative metadata
to extract automatically; this table is a mirror, in the same spirit as
``gui.config_form.CHOICES``.  It serves two purposes: (1) prompt context,
so the LLM sees each parameter's search range, and (2) it is the
optimizer's *own* hard search-space contract, enforced explicitly by
``optimize.orchestrator.Orchestrator._validate_candidate`` -- most of
``build_config``'s own checks are only "> 0" and have no notion of a
sensible upper bound (e.g. an absurd 999 nm gate length still passes
``build_config`` fine), so relying on ``build_config`` alone would let
the optimizer wander far outside the intended search space.  A stale or
too-loose bound here therefore *does* affect what the optimizer will
accept -- keep this table reviewed alongside any change to the tunable
parameter set.

Deliberately excluded, even though they are numeric fields:
- ``device.structure`` / ``polarity`` / ``external`` / ``n_fins`` /
  ``n_stacked_sheets`` / ``simulation.type``: structural/topology choices
  that change meshing or contact semantics, not device physics knobs.
- mesh density (``mesh.nx_sd`` etc.): an accuracy/speed trade-off, not a
  device-design variable -- mixing it in would let the optimizer "improve"
  a metric by under-resolving the mesh instead of changing the device.
- ``extract.icrit_a``: an *extraction* criterion, not a device parameter;
  exposing it would let the optimizer move the goalposts of its own
  objective instead of improving the device.
- ``physics.temperature`` / ``physics.dg_gamma_n/p``: temperature currently
  does not re-derive ``n_i`` (a known accuracy limitation, see
  ``docs/code_review_2026-07.md``) and dg_gamma only matters when
  ``quantum_model: density_gradient`` is on -- both need a human-reviewed
  caveat before exposing them to automated search.

This is a curated *starting* set, not an exhaustive final list -- flagged
in the plan as needing a human review pass before shipping the setup
dialog's default checklist.
"""

FIELD_BOUNDS: dict[str, dict] = {
    "device.l_gate_nm": {
        "min": 5.0, "max": 50.0, "unit": "nm",
        "description": "gate length (transport direction)",
    },
    "device.t_si_nm": {
        "min": 2.0, "max": 15.0, "unit": "nm",
        "description": "silicon body thickness",
    },
    "device.t_ox_nm": {
        "min": 0.5, "max": 3.0, "unit": "nm",
        "description": "gate oxide thickness",
    },
    "device.l_sd_nm": {
        "min": 5.0, "max": 40.0, "unit": "nm",
        "description": "source/drain extension length",
    },
    "device.junction_lambda_nm": {
        "min": 0.5, "max": 5.0, "unit": "nm",
        "description": "Gaussian decay length of the S/D doping tail",
    },
    "device.sheet_width_nm": {
        "min": 10.0, "max": 50.0, "unit": "nm",
        "description": "channel sheet width (current-scaling dimension)",
    },
    "device.t_gap_nm": {
        "min": 5.0, "max": 25.0, "unit": "nm",
        "description": "CFET stack: unmeshed spacer between the two devices",
    },
    "device.sd_doping_cm3": {
        "min": 1.0e19, "max": 5.0e20, "unit": "cm^-3",
        "description": "source/drain (degenerate) doping concentration",
    },
    "device.channel_doping_cm3": {
        "min": 1.0e14, "max": 1.0e17, "unit": "cm^-3",
        "description": "channel body doping concentration (opposite type"
                       " to source/drain)",
    },
    "device.gate_workfunction_ev": {
        "min": 3.9, "max": 5.3, "unit": "eV",
        "description": "gate metal workfunction (single-device structures)",
    },
    "device.gate_workfunction_n_ev": {
        "min": 3.9, "max": 5.3, "unit": "eV",
        "description": "CFET stack: nFET (upper device) gate workfunction",
    },
    "device.gate_workfunction_p_ev": {
        "min": 3.9, "max": 5.3, "unit": "eV",
        "description": "CFET stack: pFET (lower device) gate workfunction",
    },
    "physics.mobility_scale_n": {
        "min": 0.3, "max": 2.5, "unit": "",
        "description": "calibration multiplier on the electron low-field"
                       " mobility",
    },
    "physics.mobility_scale_p": {
        "min": 0.3, "max": 2.5, "unit": "",
        "description": "calibration multiplier on the hole low-field"
                       " mobility",
    },
}
