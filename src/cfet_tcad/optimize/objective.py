"""Objective/scoring for the LLM device-parameter optimizer.

An :class:`ObjectiveSpec` is an ordered list of metric terms (maximize or
minimize, with an optional constraint).  The LLM always sees the *raw*
per-metric values in its prompt context (built by ``optimize.prompt``) --
it is the optimizer; the scalar :class:`ScoreResult.scalar` computed here
is only a convenience for ranking/highlighting candidates in the results
table.
"""

import math
import operator
from dataclasses import dataclass, field

CONSTRAINT_OPS = {
    "<": operator.lt, "<=": operator.le,
    ">": operator.gt, ">=": operator.ge,
}


@dataclass
class ObjectiveTerm:
    #: dotted metric name (e.g. "ion_ioff_ratio"), or a fully-qualified
    #: flattened FOM key (e.g. "nFET.ion_ioff_ratio") to disambiguate a
    #: CFET stack's nFET/pFET branches.
    metric: str
    direction: str  # "maximize" | "minimize"
    constraint: tuple[str, float] | None = None
    weight: float = 1.0

    def __post_init__(self):
        if self.direction not in ("maximize", "minimize"):
            raise ValueError(
                f"direction must be 'maximize' or 'minimize', "
                f"got {self.direction!r}")
        if self.constraint is not None:
            op, _ = self.constraint
            if op not in CONSTRAINT_OPS:
                raise ValueError(
                    f"constraint op must be one of {sorted(CONSTRAINT_OPS)}"
                    f", got {op!r}")
        if self.weight <= 0:
            raise ValueError("weight must be positive")


@dataclass
class ObjectiveSpec:
    terms: list[ObjectiveTerm] = field(default_factory=list)

    def __post_init__(self):
        if not self.terms:
            raise ValueError("ObjectiveSpec needs at least one term")


@dataclass
class ScoreResult:
    scalar: float
    raw: dict  # metric -> value | None
    violations: list  # human-readable constraint-violation messages


def extract_metric(flat_fom: dict, metric: str):
    """Look up ``metric`` in a flattened FOM dict (see
    ``workflow.sweep.flatten_fom``).

    Tries an exact key match first (handles both a bare top-level metric
    and an already-qualified path like "nFET.ion_ioff_ratio").  Falls back
    to a suffix match across all keys ending in ``.<metric>`` or equal to
    it, preferring the lexicographically-last matching key -- the same
    heuristic ``workflow.sweep._pick_metric`` uses to prefer the
    saturation (largest |Vd|) curve when a metric is repeated per bias
    label.  Returns ``None`` if nothing matches.
    """
    if metric in flat_fom:
        v = flat_fom[metric]
        return float(v) if isinstance(v, (int, float)) else None
    suffix = "." + metric
    candidates = [(k, v) for k, v in flat_fom.items()
                  if (k == metric or k.endswith(suffix))
                  and isinstance(v, (int, float))]
    if not candidates:
        return None
    return float(sorted(candidates, key=lambda kv: kv[0])[-1][1])


class ObjectiveTracker:
    """Maintains running per-metric min/max across an entire optimization
    run (not per round -- round 1 has too few points to normalize
    meaningfully) and scores candidates against an :class:`ObjectiveSpec`.
    """

    def __init__(self, spec: ObjectiveSpec):
        self.spec = spec
        self._ranges: dict[str, tuple[float, float]] = {}

    def observe(self, flat_fom: dict) -> None:
        """Fold one more candidate's FOM into the running normalization
        ranges.  Call this for every candidate as its results arrive,
        before relying on :meth:`score` for that candidate."""
        for term in self.spec.terms:
            v = extract_metric(flat_fom, term.metric)
            if v is None or not math.isfinite(v):
                continue
            lo, hi = self._ranges.get(term.metric, (v, v))
            self._ranges[term.metric] = (min(lo, v), max(hi, v))

    def score(self, flat_fom: dict) -> ScoreResult:
        raw: dict = {}
        violations: list = []
        penalty = 0.0
        weighted_sum = 0.0
        weight_total = 0.0
        for term in self.spec.terms:
            v = extract_metric(flat_fom, term.metric)
            raw[term.metric] = v
            if v is None or not math.isfinite(v):
                violations.append(f"{term.metric}: missing or non-finite")
                penalty += term.weight
                continue
            if term.constraint is not None:
                op, target = term.constraint
                if not CONSTRAINT_OPS[op](v, target):
                    scale = abs(target) if target else 1.0
                    frac = abs(v - target) / scale
                    penalty += (1.0 + frac) * term.weight
                    violations.append(
                        f"{term.metric} {op} {target} violated (got {v})")
            lo, hi = self._ranges.get(term.metric, (v, v))
            norm = 0.5 if hi <= lo else (v - lo) / (hi - lo)
            if term.direction == "minimize":
                norm = 1.0 - norm
            weighted_sum += norm * term.weight
            weight_total += term.weight
        objective_score = weighted_sum / weight_total if weight_total else 0.0
        return ScoreResult(scalar=objective_score - penalty, raw=raw,
                           violations=violations)
