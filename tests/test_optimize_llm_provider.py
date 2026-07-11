import pytest

from cfet_tcad.optimize.llm_provider import (
    CandidateProposal,
    FakeProvider,
    LLMProviderError,
)


def test_fake_provider_returns_scripted_responses_in_order():
    round1 = [CandidateProposal(overrides={"device.l_gate_nm": 12.0})]
    round2 = [CandidateProposal(overrides={"device.l_gate_nm": 14.0})]
    provider = FakeProvider(responses=[round1, round2])

    got1 = provider.propose(history=[], schema={}, objective_text="",
                            n_candidates=1, best_so_far=None)
    got2 = provider.propose(history=[], schema={}, objective_text="",
                            n_candidates=1, best_so_far=None)
    assert got1 == round1
    assert got2 == round2
    assert len(provider.calls) == 2


def test_fake_provider_can_script_an_exception():
    err = LLMProviderError("boom", retryable=True)
    provider = FakeProvider(responses=[err])
    with pytest.raises(LLMProviderError, match="boom") as exc_info:
        provider.propose(history=[], schema={}, objective_text="",
                         n_candidates=1, best_so_far=None)
    assert exc_info.value.retryable is True


def test_fake_provider_raises_when_script_exhausted():
    provider = FakeProvider(responses=[])
    with pytest.raises(LLMProviderError, match="exhausted"):
        provider.propose(history=[], schema={}, objective_text="",
                         n_candidates=1, best_so_far=None)


def test_llm_provider_error_defaults_retryable_true():
    exc = LLMProviderError("transient")
    assert exc.retryable is True
    exc2 = LLMProviderError("auth failed", retryable=False)
    assert exc2.retryable is False
