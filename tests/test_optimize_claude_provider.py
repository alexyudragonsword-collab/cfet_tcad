"""ClaudeProvider tests. Two tiers:

1. Unmocked-package-availability tests (always run): exercise the real
   ImportError / missing-API-key guard paths using whatever `anthropic`
   is (or isn't) actually installed in this environment.
2. A fake `anthropic` module injected into sys.modules: exercises the
   propose()/error-mapping logic this file actually owns, without
   needing the real package or any network access.
3. A real-network smoke test, gated on ANTHROPIC_API_KEY being set
   (manual/local only, never required for CI).
"""

import os
import sys
import types

import pytest

from cfet_tcad.optimize.llm_provider import LLMProviderError
from cfet_tcad.optimize.objective import ObjectiveSpec, ObjectiveTerm

try:
    import anthropic as _real_anthropic  # noqa: F401
    _HAVE_ANTHROPIC = True
except ImportError:
    _HAVE_ANTHROPIC = False


def test_missing_package_raises_clear_llm_provider_error():
    if _HAVE_ANTHROPIC:
        pytest.skip("anthropic is installed in this environment")
    from cfet_tcad.optimize.claude_provider import ClaudeProvider

    with pytest.raises(LLMProviderError, match="anthropic") as exc_info:
        ClaudeProvider()
    assert exc_info.value.retryable is False


class _FakeAnthropicError(Exception):
    pass


class _FakeAuthError(_FakeAnthropicError):
    pass


class _FakeRateLimitError(_FakeAnthropicError):
    pass


class _FakeConnectionError(_FakeAnthropicError):
    pass


class _FakeStatusError(_FakeAnthropicError):
    def __init__(self, message, status_code):
        super().__init__(message)
        self.status_code = status_code


class _FakeToolUseBlock:
    def __init__(self, name, input_payload):
        self.type = "tool_use"
        self.name = name
        self.input = input_payload


class _FakeResponse:
    def __init__(self, content):
        self.content = content


class _FakeMessages:
    def __init__(self, create_fn):
        self._create_fn = create_fn

    def create(self, **kwargs):
        return self._create_fn(**kwargs)


class _FakeClient:
    def __init__(self, create_fn, **_kw):
        self.messages = _FakeMessages(create_fn)


def _install_fake_anthropic(monkeypatch, create_fn):
    """Inject a minimal fake `anthropic` module so ClaudeProvider's
    lazy `import anthropic` picks it up, without needing the real
    package or network access."""
    fake = types.ModuleType("anthropic")
    fake.Anthropic = lambda **kw: _FakeClient(create_fn, **kw)
    fake.AuthenticationError = _FakeAuthError
    fake.RateLimitError = _FakeRateLimitError
    fake.APIConnectionError = _FakeConnectionError
    fake.APIStatusError = _FakeStatusError
    monkeypatch.setitem(sys.modules, "anthropic", fake)
    return fake


def test_missing_api_key_raises_clear_error(monkeypatch):
    _install_fake_anthropic(monkeypatch, create_fn=lambda **kw: None)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from cfet_tcad.optimize.claude_provider import ClaudeProvider

    with pytest.raises(LLMProviderError, match="ANTHROPIC_API_KEY") as ei:
        ClaudeProvider()
    assert ei.value.retryable is False


def _spec():
    return ObjectiveSpec(terms=[
        ObjectiveTerm(metric="ion_ioff_ratio", direction="maximize")])


def test_propose_parses_tool_use_block(monkeypatch):
    def create_fn(**kwargs):
        assert kwargs["tool_choice"] == {"type": "tool",
                                         "name": "propose_candidates"}
        payload = {"candidates": [
            {"overrides": {"device.l_gate_nm": 12.0}, "rationale": "try"},
            {"overrides": {"device.l_gate_nm": 20.0}},
        ]}
        return _FakeResponse([
            _FakeToolUseBlock("propose_candidates", payload)])
    _install_fake_anthropic(monkeypatch, create_fn)
    from cfet_tcad.optimize.claude_provider import ClaudeProvider

    provider = ClaudeProvider(api_key="fake-key")
    proposals = provider.propose(
        objective=_spec(), base_values={"device.l_gate_nm": 15.0},
        history=[], best_so_far=None, n_candidates=2)
    assert len(proposals) == 2
    assert proposals[0].overrides == {"device.l_gate_nm": 12.0}
    assert proposals[0].rationale == "try"
    assert proposals[1].rationale == ""


def test_propose_maps_auth_error_to_non_retryable(monkeypatch):
    def create_fn(**kwargs):
        raise _FakeAuthError("bad key")
    fake = _install_fake_anthropic(monkeypatch, create_fn)
    from cfet_tcad.optimize.claude_provider import ClaudeProvider

    provider = ClaudeProvider(api_key="fake-key")
    with pytest.raises(LLMProviderError, match="bad key") as ei:
        provider.propose(objective=_spec(),
                         base_values={"device.l_gate_nm": 15.0},
                         history=[], best_so_far=None, n_candidates=1)
    assert ei.value.retryable is False
    assert fake.AuthenticationError is _FakeAuthError


def test_propose_maps_rate_limit_to_retryable(monkeypatch):
    def create_fn(**kwargs):
        raise _FakeRateLimitError("slow down")
    _install_fake_anthropic(monkeypatch, create_fn)
    from cfet_tcad.optimize.claude_provider import ClaudeProvider

    provider = ClaudeProvider(api_key="fake-key")
    with pytest.raises(LLMProviderError, match="slow down") as ei:
        provider.propose(objective=_spec(),
                         base_values={"device.l_gate_nm": 15.0},
                         history=[], best_so_far=None, n_candidates=1)
    assert ei.value.retryable is True


def test_propose_maps_5xx_status_to_retryable_4xx_to_not(monkeypatch):
    from cfet_tcad.optimize.claude_provider import ClaudeProvider

    _install_fake_anthropic(
        monkeypatch, create_fn=lambda **kw: (_ for _ in ()).throw(
            _FakeStatusError("server error", 500)))
    provider = ClaudeProvider(api_key="fake-key")
    with pytest.raises(LLMProviderError) as ei:
        provider.propose(objective=_spec(),
                         base_values={"device.l_gate_nm": 15.0},
                         history=[], best_so_far=None, n_candidates=1)
    assert ei.value.retryable is True

    _install_fake_anthropic(
        monkeypatch, create_fn=lambda **kw: (_ for _ in ()).throw(
            _FakeStatusError("bad request", 400)))
    provider = ClaudeProvider(api_key="fake-key")
    with pytest.raises(LLMProviderError) as ei:
        provider.propose(objective=_spec(),
                         base_values={"device.l_gate_nm": 15.0},
                         history=[], best_so_far=None, n_candidates=1)
    assert ei.value.retryable is False


def test_propose_no_tool_use_block_is_retryable(monkeypatch):
    _install_fake_anthropic(
        monkeypatch, create_fn=lambda **kw: _FakeResponse([]))
    from cfet_tcad.optimize.claude_provider import ClaudeProvider

    provider = ClaudeProvider(api_key="fake-key")
    with pytest.raises(LLMProviderError, match="no tool_use") as ei:
        provider.propose(objective=_spec(),
                         base_values={"device.l_gate_nm": 15.0},
                         history=[], best_so_far=None, n_candidates=1)
    assert ei.value.retryable is True


def test_propose_malformed_payload_is_retryable(monkeypatch):
    _install_fake_anthropic(
        monkeypatch, create_fn=lambda **kw: _FakeResponse([
            _FakeToolUseBlock("propose_candidates", {"oops": []})]))
    from cfet_tcad.optimize.claude_provider import ClaudeProvider

    provider = ClaudeProvider(api_key="fake-key")
    with pytest.raises(LLMProviderError, match="malformed") as ei:
        provider.propose(objective=_spec(),
                         base_values={"device.l_gate_nm": 15.0},
                         history=[], best_so_far=None, n_candidates=1)
    assert ei.value.retryable is True


@pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"),
                    reason="requires a real ANTHROPIC_API_KEY "
                           "(manual/local only)")
def test_real_claude_api_returns_valid_candidates():
    pytest.importorskip("anthropic")
    from cfet_tcad.optimize.claude_provider import ClaudeProvider

    provider = ClaudeProvider()
    proposals = provider.propose(
        objective=_spec(), base_values={"device.l_gate_nm": 15.0},
        history=[], best_so_far=None, n_candidates=2)
    assert 1 <= len(proposals) <= 2
    for p in proposals:
        assert p.overrides
        assert all(isinstance(v, (int, float)) for v in p.overrides.values())
