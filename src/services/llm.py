"""LLM Service — multi-provider wrapper around LangChain chat/embedding models.

WHY a wrapper instead of importing `ChatOpenAI` (or `ChatAnthropic`, etc.)
directly in every agent node?
  1. Provider swap without code changes: set LLM_PROVIDER=anthropic in the
     environment and every agent picks up Claude instead of GPT-4o, with no
     import changes anywhere else in the codebase (see ADR-06 in
     docs/architecture/system_architecture.md).
  2. One place to configure retry/timeout/temperature defaults consistently.
  3. One place to keep API keys out of code (`src/config.py` reads them from
     env vars — never hardcode a key here or anywhere else).

Every chat model returned here implements LangChain's `BaseChatModel`
interface (`.invoke()`, `.ainvoke()`, `.with_structured_output()`, ...), so
calling code never needs to know which vendor is actually behind it.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from src.config import settings

logger = logging.getLogger(__name__)

# Providers this service knows how to build a chat model / embeddings for.
# "claude" and "gemini" are accepted as friendly aliases for
# "anthropic" / "google" so a student typing LLM_PROVIDER=claude in .env
# doesn't hit a confusing error.
_PROVIDER_ALIASES = {
    "openai": "openai",
    "anthropic": "anthropic",
    "claude": "anthropic",
    "google": "google",
    "gemini": "google",
}


def _normalize_provider(provider: str) -> str:
    key = (provider or "").strip().lower()
    normalized = _PROVIDER_ALIASES.get(key)
    if not normalized:
        supported = ", ".join(sorted(set(_PROVIDER_ALIASES.values())))
        raise ValueError(f"Unsupported LLM_PROVIDER '{provider}'. Supported providers: {supported}.")
    return normalized


def _is_retryable_error(exc: BaseException) -> bool:
    """Decide whether an exception from an LLM call is worth retrying.

    WHY check by *behavior* (timeout / rate limit / connection) instead of a
    hardcoded exception list? Each provider SDK (openai, anthropic,
    google-genai) defines its own exception classes, and we don't want this
    file to hard-require all three packages just to build a retry predicate.
    We import each SDK's error types lazily and only check the ones that are
    actually installed; anything else (e.g. a 400 Bad Request / auth error)
    is NOT retried because retrying a broken request just wastes API calls.
    """
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return True

    try:
        import openai as _openai

        if isinstance(exc, (_openai.RateLimitError, _openai.APITimeoutError, _openai.APIConnectionError)):
            return True
    except ImportError:
        pass

    try:
        import anthropic as _anthropic

        if isinstance(exc, (_anthropic.RateLimitError, _anthropic.APITimeoutError, _anthropic.APIConnectionError)):
            return True
    except ImportError:
        pass

    try:
        from google.genai import errors as _google_errors

        # Google's SDK doesn't split "rate limited" into its own exception
        # class the way OpenAI/Anthropic do — a 429 arrives as a ClientError
        # with `.code == 429`, so we check the status code explicitly.
        if isinstance(exc, _google_errors.ServerError):
            return True
        if isinstance(exc, _google_errors.ClientError) and getattr(exc, "code", None) == 429:
            return True
    except ImportError:
        pass

    return False


def _llm_retry(func):
    """Retry decorator: exponential backoff, up to LLM_MAX_RETRIES attempts.

    Applied to the network call itself (not the whole agent node) so a
    transient rate-limit/timeout on one LLM call doesn't need the caller to
    implement its own retry loop.
    """
    return retry(
        reraise=True,
        stop=stop_after_attempt(max(1, settings.LLM_MAX_RETRIES)),
        wait=wait_exponential(multiplier=1, min=1, max=20),
        retry=retry_if_exception(_is_retryable_error),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )(func)


def _build_openai_chat(*, model: str, temperature: float, api_key: str, **kwargs: Any) -> BaseChatModel:
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=model,
        temperature=temperature,
        api_key=api_key or None,
        timeout=settings.LLM_TIMEOUT_SECONDS,
        max_retries=0,  # we retry ourselves via `_llm_retry`, avoid double-retrying
        **kwargs,
    )


def _build_anthropic_chat(*, model: str, temperature: float, api_key: str, **kwargs: Any) -> BaseChatModel:
    from langchain_anthropic import ChatAnthropic

    return ChatAnthropic(
        model=model,
        temperature=temperature,
        api_key=api_key or None,
        timeout=settings.LLM_TIMEOUT_SECONDS,
        max_retries=0,
        **kwargs,
    )


def _build_google_chat(*, model: str, temperature: float, api_key: str, **kwargs: Any) -> BaseChatModel:
    from langchain_google_genai import ChatGoogleGenerativeAI

    return ChatGoogleGenerativeAI(
        model=model,
        temperature=temperature,
        api_key=api_key or None,
        timeout=settings.LLM_TIMEOUT_SECONDS,
        max_retries=0,
        **kwargs,
    )


_CHAT_BUILDERS = {
    "openai": _build_openai_chat,
    "anthropic": _build_anthropic_chat,
    "google": _build_google_chat,
}

# Sane default model per provider, used only when the caller/env doesn't
# specify LLM_MODEL — keeps `get_llm()` usable with zero configuration
# besides an API key.
_DEFAULT_MODEL = {
    "openai": "gpt-4o",
    "anthropic": "claude-sonnet-4-5-20250929",
    "google": "gemini-2.0-flash",
}


@lru_cache(maxsize=8)
def _cached_llm(provider: str, model: str, temperature: float) -> BaseChatModel:
    """Build (and memoize) a chat model instance.

    WHY cache? Creating a new `ChatOpenAI(...)` object per LLM call is cheap
    but not free (it re-parses config each time); caching by
    (provider, model, temperature) means repeated calls with the same
    settings reuse one client instance.
    """
    api_key = settings.get_provider_api_key(provider)
    if not api_key:
        raise ValueError(
            f"No API key configured for provider '{provider}'. "
            f"Set {provider.upper()}_API_KEY (or the generic LLM_API_KEY) in your environment."
        )
    builder = _CHAT_BUILDERS[provider]
    return builder(model=model, temperature=temperature, api_key=api_key)


def get_llm(
    *,
    provider: str | None = None,
    model: str | None = None,
    temperature: float | None = None,
) -> BaseChatModel:
    """Return a configured chat model for the given (or default) provider.

    Any argument left as None falls back to `src/config.py` settings, which
    in turn read from environment variables (LLM_PROVIDER, LLM_MODEL,
    LLM_TEMPERATURE). This is the single entry point agent nodes should use
    instead of importing ChatOpenAI/ChatAnthropic/ChatGoogleGenerativeAI
    directly.

    The returned retrying behavior is transparent: call `.invoke(...)` /
    `.ainvoke(...)` as usual — retries on rate limits/timeouts happen
    automatically underneath via LangChain's `.with_retry()`.
    """
    resolved_provider = _normalize_provider(provider or settings.LLM_PROVIDER)
    resolved_model = model or (settings.LLM_MODEL if provider is None else None) or _DEFAULT_MODEL[resolved_provider]
    resolved_temperature = settings.LLM_TEMPERATURE if temperature is None else temperature

    llm = _cached_llm(resolved_provider, resolved_model, resolved_temperature)
    # `.with_retry()` wraps the LangChain model so every `.invoke`/`.ainvoke`
    # call goes through our retry predicate — this is on top of (not
    # instead of) the `_llm_retry` decorator used for plain function calls
    # elsewhere in this module (e.g. embeddings).
    return llm.with_retry(
        retry_if_exception_type=(Exception,),
        stop_after_attempt=max(1, settings.LLM_MAX_RETRIES),
        wait_exponential_jitter=True,
    )


def _build_openai_embeddings(*, model: str, api_key: str) -> Embeddings:
    from langchain_openai import OpenAIEmbeddings

    return OpenAIEmbeddings(model=model, api_key=api_key or None)


def _build_google_embeddings(*, model: str, api_key: str) -> Embeddings:
    from langchain_google_genai import GoogleGenerativeAIEmbeddings

    return GoogleGenerativeAIEmbeddings(model=model, google_api_key=api_key or None)


_EMBEDDING_BUILDERS = {
    "openai": _build_openai_embeddings,
    "google": _build_google_embeddings,
}


@lru_cache(maxsize=4)
def get_embeddings(*, provider: str | None = None, model: str | None = None) -> Embeddings:
    """Return a configured embeddings model, used for Qdrant vector search.

    WHY separate from `get_llm()`? Embeddings and chat completions are
    different API calls with different models (e.g. OpenAI's
    "text-embedding-3-small" vs "gpt-4o"); Anthropic does not offer an
    embeddings endpoint, so "anthropic"/"claude" is not a valid embedding
    provider — pick "openai" or "google" instead.
    """
    resolved_provider = _normalize_provider(provider or settings.EMBEDDING_PROVIDER)
    if resolved_provider not in _EMBEDDING_BUILDERS:
        raise ValueError(
            f"Provider '{resolved_provider}' has no embeddings support in this service. "
            f"Use one of: {', '.join(_EMBEDDING_BUILDERS)}."
        )
    resolved_model = model or settings.EMBEDDING_MODEL
    api_key = settings.get_provider_api_key(resolved_provider)
    if not api_key:
        raise ValueError(
            f"No API key configured for embeddings provider '{resolved_provider}'. "
            f"Set {resolved_provider.upper()}_API_KEY (or the generic LLM_API_KEY) in your environment."
        )
    return _EMBEDDING_BUILDERS[resolved_provider](model=resolved_model, api_key=api_key)


@_llm_retry
def invoke_with_retry(llm: BaseChatModel, messages: list[Any]) -> Any:
    """Explicit retrying sync call, for code that builds its own LLM instance
    (e.g. via `_cached_llm` directly) instead of going through `get_llm()`.

    Most callers should just use `get_llm(...).invoke(...)` — the model
    returned by `get_llm()` already retries via `.with_retry()`. This
    helper exists for the rare case of wanting the retry behavior without
    the `.with_retry()` wrapper (e.g. when composing with
    `.with_structured_output()`, which some LangChain versions don't
    preserve retry config through cleanly).
    """
    return llm.invoke(messages)
