"""Fábrica de adapters LLM. Padrão: mock (sem custo, sem envio de dados)."""
from __future__ import annotations

from ..config import Settings
from .mock import MockLlm
from .providers import (AnthropicLlm, GeminiLlm, LlmError, LlmProvider, LlmResponse, LocalLlm,
                        OpenAiCompatibleLlm, parse_json)


def build_llm(settings: Settings) -> LlmProvider:
    settings.check_ai_policy()
    p = settings.llm_provider
    kw = dict(model=settings.llm_model, api_key=settings.llm_api_key, base_url=settings.llm_base_url,
              timeout_s=settings.llm_timeout_s, temperature=settings.llm_temperature)
    if p == "mock":
        return MockLlm()
    if p == "local":
        return LocalLlm(**kw)
    if p == "openai":
        return OpenAiCompatibleLlm(**kw)
    if p == "anthropic":
        return AnthropicLlm(**kw)
    if p == "gemini":
        return GeminiLlm(**kw)
    raise LlmError(f"LLM_PROVIDER desconhecido: {p}", permanent=True, code="config")


__all__ = ["build_llm", "LlmError", "LlmProvider", "LlmResponse", "MockLlm", "parse_json"]
