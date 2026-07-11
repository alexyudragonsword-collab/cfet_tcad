"""LLM-assisted device-parameter optimization (pure-Python core).

This package's top-level exports are pure Python -- no PySide6, no
``anthropic`` -- so it imports cleanly without the ``[gui]``/``[llm]``
extras installed.  The Qt-dependent round-loop orchestration
(``orchestrator``/``llm_worker``) and the concrete Claude adapter
(``claude_provider``) are separate modules the GUI imports lazily.
"""

from .llm_provider import (
    CandidateProposal,
    FakeProvider,
    LLMProvider,
    LLMProviderError,
    RoundRecord,
)
from .objective import ObjectiveSpec, ObjectiveTerm, ObjectiveTracker, ScoreResult
from .schema import FIELD_BOUNDS

__all__ = [
    "CandidateProposal",
    "FakeProvider",
    "LLMProvider",
    "LLMProviderError",
    "RoundRecord",
    "ObjectiveSpec",
    "ObjectiveTerm",
    "ObjectiveTracker",
    "ScoreResult",
    "FIELD_BOUNDS",
]
