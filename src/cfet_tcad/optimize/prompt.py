"""Prompt construction for the LLM device-parameter optimizer.

Kept pure-Python and provider-agnostic: :func:`build_round_prompt` returns
plain text plus a JSON-schema dict for structured output; a concrete
:class:`~optimize.llm_provider.LLMProvider` translates that into its own
API's request shape (see ``optimize.claude_provider``).
"""

import json

from .llm_provider import RoundRecord
from .objective import ObjectiveSpec
from .schema import FIELD_BOUNDS

SYSTEM_PROMPT = """\
You are the search strategy for an automated semiconductor-device \
parameter optimizer. A separate tool takes the parameter values you \
propose, validates them, runs a real TCAD (drift-diffusion) simulation, \
and reports back the resulting figures of merit. You do not run any \
simulation yourself and you do not write code -- you only propose \
parameter values as structured JSON.

Rules:
- Only propose dotted-path keys that appear in the "tunable parameters" \
list you are given; any other key will be rejected before simulation.
- Stay within each parameter's stated [min, max] bounds.
- Propose genuinely different candidates from each other and from every \
candidate already tried in the history below -- do not repeat a prior \
point, and prefer exploring under-sampled regions of the search space \
unless the history strongly points toward refining near the current best.
- Reason about the physical trade-offs implied by the objective and the \
history; you are the optimizer, not a random sampler.
"""

#: JSON Schema for structured-output extraction (see build_round_prompt).
#: Numeric bounds are NOT expressible here (most providers' structured-
#: output subsets omit minimum/maximum) -- bounds are prose-only in the
#: prompt; the real enforcement is workflow.config.build_config downstream.
RESPONSE_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "overrides": {
                        "type": "object",
                        "description": "dotted-path parameter name -> "
                                       "proposed numeric value",
                    },
                    "rationale": {"type": "string"},
                },
                "required": ["overrides"],
            },
        },
    },
    "required": ["candidates"],
}


def _format_objective(spec: ObjectiveSpec) -> str:
    lines = []
    for term in spec.terms:
        piece = f"- {term.direction} {term.metric}"
        if term.constraint is not None:
            op, target = term.constraint
            piece += f", constrained to {term.metric} {op} {target}"
        lines.append(piece)
    return "\n".join(lines)


def _format_tunable_params(base_values: dict) -> str:
    lines = []
    for path, bound in FIELD_BOUNDS.items():
        current = base_values.get(path, "?")
        unit = bound.get("unit", "")
        lines.append(
            f"- {path}: min={bound['min']}, max={bound['max']}"
            f"{f' {unit}' if unit else ''}, current={current}"
            f" -- {bound['description']}")
    return "\n".join(lines)


def _format_history(history: list) -> str:
    if not history:
        return "(no candidates tried yet -- this is round 1)"
    lines = []
    for i, rec in enumerate(history):
        lines.append(
            f"[{i}] overrides={json.dumps(rec.overrides, sort_keys=True)} "
            f"status={rec.status} score={rec.score} "
            f"fom={json.dumps(rec.fom, sort_keys=True)}")
    return "\n".join(lines)


def build_round_prompt(*, objective: ObjectiveSpec, base_values: dict,
                       history: list, best_so_far,
                       n_candidates: int,
                       repair_context: str | None = None,
                       ) -> tuple[str, str, dict]:
    """Build one round's prompt.

    ``base_values`` maps every ``FIELD_BOUNDS`` key to the base config's
    current value (so the LLM knows the starting point).  ``history`` is
    a list of :class:`~optimize.llm_provider.RoundRecord` accumulated
    across all prior rounds.  ``best_so_far`` is a ``RoundRecord`` or
    ``None``.  ``repair_context``, when given, requests replacements only
    for specific rejected candidates rather than a fresh full batch.

    Returns ``(system_prompt, user_prompt, response_json_schema)``.
    """
    parts = [
        "## Objective\n" + _format_objective(objective),
        "## Tunable parameters\n" + _format_tunable_params(base_values),
        "## History (all candidates tried so far)\n"
        + _format_history(history),
    ]
    if best_so_far is not None:
        parts.append(
            "## Best result so far\n"
            f"overrides={json.dumps(best_so_far.overrides, sort_keys=True)} "
            f"score={best_so_far.score} "
            f"fom={json.dumps(best_so_far.fom, sort_keys=True)}")
    if repair_context:
        parts.append(
            "## Repair needed\n" + repair_context + "\n\n"
            "Propose replacement candidates ONLY for the rejected slots "
            "above, using the same overrides/rationale JSON shape.")
    else:
        parts.append(f"Propose {n_candidates} new candidate(s) for this "
                     f"round.")
    user_prompt = "\n\n".join(parts)
    return SYSTEM_PROMPT, user_prompt, RESPONSE_JSON_SCHEMA
