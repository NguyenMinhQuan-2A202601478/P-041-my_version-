"""Tests for src/services/llm.py — the multi-provider LLM wrapper (ADR-06).

None of these tests make a real network call: the per-provider builder
functions (`_build_openai_chat`, etc.) are monkeypatched to return a
`MagicMock` standing in for a LangChain `BaseChatModel`, so we can assert on
*how* `get_llm()` builds/configures a model without needing real API keys or
hitting a real provider.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.services import llm as llm_module
from src.services.llm import _is_retryable_error, get_llm


@pytest.fixture(autouse=True)
def _clear_llm_cache():
    """`_cached_llm` is `lru_cache`d at module scope — clear it around every
    test so one test's monkeypatched builder can't leak into another via a
    cached (provider, model, temperature) key."""
    llm_module._cached_llm.cache_clear()
    yield
    llm_module._cached_llm.cache_clear()


@pytest.fixture()
def mock_builders(monkeypatch):
    """Replace every provider's chat-model builder with a MagicMock and
    return the dict of mocks, keyed by provider name."""
    mocks = {provider: MagicMock(name=f"build_{provider}_chat") for provider in llm_module._CHAT_BUILDERS}
    for provider, mock in mocks.items():
        monkeypatch.setattr(llm_module, "_CHAT_BUILDERS", {**llm_module._CHAT_BUILDERS, provider: mock})
    return mocks


@pytest.mark.parametrize(
    "provider,env_attr",
    [
        ("openai", "OPENAI_API_KEY"),
        ("anthropic", "ANTHROPIC_API_KEY"),
        ("google", "GOOGLE_API_KEY"),
    ],
)
def test_get_llm_builds_the_configured_provider(monkeypatch, mock_builders, provider, env_attr):
    monkeypatch.setattr(llm_module.settings, env_attr, "fake-api-key")

    result = get_llm(provider=provider, model="test-model", temperature=0.1)

    mock_builders[provider].assert_called_once()
    call_kwargs = mock_builders[provider].call_args.kwargs
    assert call_kwargs["model"] == "test-model"
    assert call_kwargs["temperature"] == 0.1
    assert call_kwargs["api_key"] == "fake-api-key"
    # get_llm() must return the `.with_retry(...)`-wrapped model, not the
    # raw builder output.
    assert result is mock_builders[provider].return_value.with_retry.return_value


@pytest.mark.parametrize("alias,canonical", [("claude", "anthropic"), ("gemini", "google")])
def test_get_llm_accepts_friendly_provider_aliases(monkeypatch, mock_builders, alias, canonical):
    env_attr = "ANTHROPIC_API_KEY" if canonical == "anthropic" else "GOOGLE_API_KEY"
    monkeypatch.setattr(llm_module.settings, env_attr, "fake-api-key")

    get_llm(provider=alias, model="test-model")

    mock_builders[canonical].assert_called_once()


def test_get_llm_raises_for_unsupported_provider(mock_builders):
    with pytest.raises(ValueError, match="Unsupported LLM_PROVIDER"):
        get_llm(provider="not-a-real-provider")


def test_get_llm_raises_when_no_api_key_is_configured(monkeypatch, mock_builders):
    monkeypatch.setattr(llm_module.settings, "OPENAI_API_KEY", "")
    monkeypatch.setattr(llm_module.settings, "LLM_API_KEY", "")

    with pytest.raises(ValueError, match="No API key configured"):
        get_llm(provider="openai", model="test-model")


def test_get_llm_falls_back_to_generic_llm_api_key(monkeypatch, mock_builders):
    monkeypatch.setattr(llm_module.settings, "OPENAI_API_KEY", "")
    monkeypatch.setattr(llm_module.settings, "LLM_API_KEY", "generic-fallback-key")

    get_llm(provider="openai", model="test-model")

    assert mock_builders["openai"].call_args.kwargs["api_key"] == "generic-fallback-key"


def test_get_llm_uses_default_model_when_none_given(monkeypatch, mock_builders):
    monkeypatch.setattr(llm_module.settings, "OPENAI_API_KEY", "fake-key")

    get_llm(provider="openai")

    assert mock_builders["openai"].call_args.kwargs["model"] == llm_module._DEFAULT_MODEL["openai"]


# ---------------------------------------------------------------------------
# Retry configuration
# ---------------------------------------------------------------------------
def test_get_llm_configures_retry_with_llm_max_retries(monkeypatch, mock_builders):
    monkeypatch.setattr(llm_module.settings, "OPENAI_API_KEY", "fake-key")
    monkeypatch.setattr(llm_module.settings, "LLM_MAX_RETRIES", 7)

    get_llm(provider="openai", model="test-model")

    with_retry_mock = mock_builders["openai"].return_value.with_retry
    with_retry_mock.assert_called_once()
    kwargs = with_retry_mock.call_args.kwargs
    assert kwargs["stop_after_attempt"] == 7
    assert kwargs["retry_if_exception_type"] == (Exception,)
    assert kwargs["wait_exponential_jitter"] is True


def test_get_llm_retry_attempts_floored_at_one(monkeypatch, mock_builders):
    monkeypatch.setattr(llm_module.settings, "OPENAI_API_KEY", "fake-key")
    monkeypatch.setattr(llm_module.settings, "LLM_MAX_RETRIES", 0)

    get_llm(provider="openai", model="test-model")

    kwargs = mock_builders["openai"].return_value.with_retry.call_args.kwargs
    assert kwargs["stop_after_attempt"] == 1


# ---------------------------------------------------------------------------
# _is_retryable_error — pure predicate, no mocking needed
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("exc", [TimeoutError("timed out"), ConnectionError("connection reset")])
def test_is_retryable_error_true_for_timeout_and_connection_errors(exc):
    assert _is_retryable_error(exc) is True


@pytest.mark.parametrize("exc", [ValueError("bad request"), KeyError("missing"), RuntimeError("boom")])
def test_is_retryable_error_false_for_generic_errors(exc):
    assert _is_retryable_error(exc) is False
