"""QThread-hosted wrapper around a blocking LLMProvider.propose() call.

A provider's ``propose()`` is a blocking network call (or, for
``FakeProvider``, an instant in-process call) -- either way it must never
run on the Qt GUI thread.  ``LLMWorker`` is moved onto its own
``QThread`` by :class:`~optimize.orchestrator.Orchestrator`; it must only
ever be driven by emitting the orchestrator's ``_request_propose`` signal
(which Qt auto-marshals across threads), never by calling
:meth:`run_propose` directly from the GUI thread -- a direct call would
still execute on the caller's thread and defeat the whole point.
"""

from PySide6.QtCore import QObject, Signal

from .llm_provider import LLMProvider, LLMProviderError


class LLMWorker(QObject):
    proposal_ready = Signal(list)        # list[CandidateProposal]
    proposal_failed = Signal(str, bool)  # (message, retryable)

    def __init__(self, provider: LLMProvider):
        super().__init__()
        self.provider = provider

    def run_propose(self, kwargs: dict) -> None:
        try:
            proposals = self.provider.propose(**kwargs)
        except LLMProviderError as exc:
            self.proposal_failed.emit(str(exc), exc.retryable)
        except Exception as exc:  # noqa: BLE001 - never crash the worker thread
            self.proposal_failed.emit(f"unexpected provider error: {exc}",
                                      False)
        else:
            self.proposal_ready.emit(list(proposals))
