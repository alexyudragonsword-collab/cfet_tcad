"""Claude (Anthropic) adapter.

Turns ``optimize.prompt.build_round_prompt``'s system/user text + JSON
response schema into a single tool-call request (Claude has no separate
"response_format"/JSON-mode parameter; forcing a named tool call is the
reliable way to get schema-constrained structured output from the
Messages API) and parses the result back into ``CandidateProposal``
objects.

The ``anthropic`` package is only imported inside ``__init__`` (lazily),
so importing this module -- or anything else in ``optimize.*`` -- never
requires the ``[llm]`` extra to be installed; selecting "Claude" in the
GUI without it raises a clear, dialog-displayable
:class:`~optimize.llm_provider.LLMProviderError` instead of an
``ImportError`` deep in a signal handler.
"""

import os

from .llm_provider import CandidateProposal, LLMProvider, LLMProviderError
from .objective import ObjectiveSpec
from .prompt import build_round_prompt

#: forcing this one named tool is what makes the response structured
_TOOL_NAME = "propose_candidates"

#: a well-specified, repeated structured-extraction task -- cost/latency
#: matter more than open-ended reasoning depth, so Sonnet over Opus
DEFAULT_MODEL = "claude-sonnet-5"


class ClaudeProvider(LLMProvider):
    """LLMProvider backed by the Anthropic Claude API.

    Reads the API key from the ``ANTHROPIC_API_KEY`` environment variable
    (the SDK's own default resolution) unless ``api_key`` is given
    explicitly.  Raises ``LLMProviderError(retryable=False)`` immediately
    on construction if the SDK is missing or no key is configured, so a
    bad setup fails on round 1 instead of after a long retry loop.
    """

    def __init__(self, model: str = DEFAULT_MODEL,
                api_key: str | None = None, max_tokens: int = 4096,
                request_timeout_s: float = 60.0):
        try:
            import anthropic
        except ImportError as exc:
            raise LLMProviderError(
                "the 'anthropic' package is not installed - "
                "pip install 'cfet-tcad[llm]'", retryable=False) from exc
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise LLMProviderError(
                "ANTHROPIC_API_KEY is not set", retryable=False)
        self.model = model
        self.max_tokens = max_tokens
        self._anthropic = anthropic
        self._client = anthropic.Anthropic(api_key=key,
                                           timeout=request_timeout_s)

    def propose(self, *, objective: ObjectiveSpec, base_values: dict,
               history: list, best_so_far, n_candidates: int,
               repair_context: str | None = None) -> list:
        system, user, schema = build_round_prompt(
            objective=objective, base_values=base_values, history=history,
            best_so_far=best_so_far, n_candidates=n_candidates,
            repair_context=repair_context)
        tool = {
            "name": _TOOL_NAME,
            "description": "Propose semiconductor device parameter"
                           " candidates for a TCAD optimization round.",
            "input_schema": schema,
        }
        a = self._anthropic
        try:
            response = self._client.messages.create(
                model=self.model, max_tokens=self.max_tokens, system=system,
                messages=[{"role": "user", "content": user}], tools=[tool],
                tool_choice={"type": "tool", "name": _TOOL_NAME})
        except a.AuthenticationError as exc:
            raise LLMProviderError(str(exc), retryable=False) from exc
        except a.RateLimitError as exc:
            raise LLMProviderError(str(exc), retryable=True) from exc
        except a.APIConnectionError as exc:
            raise LLMProviderError(str(exc), retryable=True) from exc
        except a.APIStatusError as exc:
            # 4xx (other than the two caught above) is unlikely to
            # resolve on retry; 5xx usually will
            retryable = getattr(exc, "status_code", 500) >= 500
            raise LLMProviderError(str(exc), retryable=retryable) from exc
        except Exception as exc:  # noqa: BLE001 - never let this escape raw
            raise LLMProviderError(f"unexpected Claude API error: {exc}",
                                   retryable=True) from exc

        payload = None
        for block in response.content:
            if getattr(block, "type", None) == "tool_use" \
                    and block.name == _TOOL_NAME:
                payload = block.input
                break
        if payload is None:
            raise LLMProviderError(
                "Claude response contained no tool_use block for "
                f"{_TOOL_NAME!r}", retryable=True)

        try:
            proposals = [
                CandidateProposal(overrides=dict(c["overrides"]),
                                  rationale=c.get("rationale", ""))
                for c in payload["candidates"]]
        except (KeyError, TypeError) as exc:
            raise LLMProviderError(
                f"malformed candidate payload: {exc}", retryable=True) from exc
        return proposals
