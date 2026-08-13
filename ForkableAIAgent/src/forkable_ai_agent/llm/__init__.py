"""LLM package: pick the best locally available brain."""

from __future__ import annotations

from typing import Any

from ..config import Settings
from .base import LLMClient, LLMResponse, LLMUnavailable
from .ollama_client import OllamaLLM
from .rules import RuleBasedLLM, nl_to_plan_dict

__all__ = [
    "LLMClient",
    "LLMResponse",
    "LLMUnavailable",
    "OllamaLLM",
    "RuleBasedLLM",
    "build_llm",
    "nl_to_plan_dict",
]


def build_llm(settings: Settings, probe: bool = True) -> Any:
    """Return a live Ollama client, or the deterministic engine as fallback.

    ``probe=False`` skips the liveness check (useful in unit tests).
    """
    if settings.llm.provider == "none":
        return RuleBasedLLM(embed_dim=settings.rag.embed_dim)

    try:
        client = OllamaLLM(
            base_url=settings.llm.base_url,
            model=settings.llm.model,
            embed_model=settings.llm.embed_model,
            temperature=settings.llm.temperature,
            timeout_s=settings.llm.timeout_s,
            num_ctx=settings.llm.num_ctx,
        )
    except ValueError:
        return RuleBasedLLM(embed_dim=settings.rag.embed_dim)

    if probe and not client.available():
        if not settings.llm.allow_rule_based_fallback:
            raise LLMUnavailable(
                f"no Ollama daemon at {settings.llm.base_url}; start it with 'ollama serve'"
            )
        return RuleBasedLLM(embed_dim=settings.rag.embed_dim)

    if probe:
        client.resolve_model(settings.llm.model_preferences)
        client.resolve_embed_model(settings.llm.embed_preferences)
    return client
