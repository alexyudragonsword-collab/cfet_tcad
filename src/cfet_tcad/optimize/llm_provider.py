"""Vendor-agnostic LLM adapter interface for the device-parameter
optimizer.

A provider's only job is: given the running optimization state (objective,
tunable-parameter schema, and the full round-by-round history), return N
candidate parameter proposals.  It knows nothing about DEVSIM, RunQueue,
or Qt -- that keeps the interface trivially mockable (:class:`FakeProvider`
is what the orchestrator's tests drive) and lets a second vendor be added
later without touching the orchestrator.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from .objective import ObjectiveSpec


@dataclass
class CandidateProposal:
    #: dotted-path parameter -> proposed value, e.g.
    #: {"device.l_gate_nm": 12.0, "physics.mobility_scale_n": 1.05}
    overrides: dict
    rationale: str = ""


@dataclass(eq=False)  # identity semantics: hashable, usable as a dict key
class RoundRecord:
    """One completed candidate, in the shape shown back to the LLM as
    history and used by the results table."""
    overrides: dict
    status: str  # "ok" | "rejected: <reason>" | "error: <reason>"
    fom: dict = field(default_factory=dict)  # flattened FOM; empty if not ok
    score: float | None = None


class LLMProviderError(RuntimeError):
    """Raised by a provider on any failure: network error, malformed
    response, auth failure, etc.  ``retryable`` tells the orchestrator
    whether retrying the same request is worth attempting (network/rate
    limit/parse errors: yes; auth errors: no)."""

    def __init__(self, message: str, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


class LLMProvider(ABC):
    """Propose parameter candidates given the current optimization state.

    A concrete provider typically builds its request by handing these same
    keyword arguments straight to ``optimize.prompt.build_round_prompt``
    (which returns a system/user prompt pair plus a JSON response schema)
    and then makes its own API call -- see ``optimize.claude_provider``.
    """

    @abstractmethod
    def propose(self, *, objective: ObjectiveSpec, base_values: dict,
               history: list, best_so_far, n_candidates: int,
               repair_context: str | None = None) -> list:
        """Return up to ``n_candidates`` :class:`CandidateProposal`.

        ``objective`` is the scoring spec.  ``base_values`` maps every
        ``optimize.schema.FIELD_BOUNDS`` key to the base config's current
        value.  ``history`` is a list of :class:`RoundRecord` from all
        prior rounds/repairs.  ``best_so_far`` is a :class:`RoundRecord`
        or ``None``.  ``repair_context``, when given, describes specific
        candidates the caller just rejected (with reasons) and asks for
        replacements only for those slots -- used by the in-round
        validation-retry loop.

        Must raise :class:`LLMProviderError` on any failure rather than
        letting a provider-specific exception escape.
        """


class FakeProvider(LLMProvider):
    """Deterministic provider for tests: returns a fixed, pre-scripted
    sequence of responses, one script entry consumed per :meth:`propose`
    call regardless of the arguments given.  Each entry is either a list
    of :class:`CandidateProposal` or an :class:`Exception` instance/class
    to raise."""

    def __init__(self, responses: list):
        self._responses = list(responses)
        self._i = 0
        #: recorded kwargs of every propose() call, for test assertions
        self.calls: list[dict] = []

    def propose(self, **kwargs):
        self.calls.append(kwargs)
        if self._i >= len(self._responses):
            raise LLMProviderError(
                "FakeProvider script exhausted", retryable=False)
        item = self._responses[self._i]
        self._i += 1
        if isinstance(item, Exception):
            raise item
        return item
