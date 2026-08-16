"""LLM abstraction.

Two implementations ship with the agent:

* :class:`~forkable_ai_agent.llm.ollama_client.OllamaLLM` - a local Ollama
  daemon on loopback (llama3, qwen2.5-coder, mistral, phi, ...).
* :class:`~forkable_ai_agent.llm.rules.RuleBasedLLM` - a deterministic engine
  used when no daemon is running, so the agent degrades instead of dying.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class LLMResponse:
    text: str
    model: str = ""
    latency_ms: float = 0.0
    meta: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:  # pragma: no cover - convenience only
        return self.text


class LLMUnavailable(RuntimeError):
    """The configured local model could not be reached."""


@runtime_checkable
class LLMClient(Protocol):
    """Minimal surface the agent needs from a language model."""

    name: str

    def available(self) -> bool:
        """Cheap liveness probe; must never raise."""

    def generate(
        self,
        prompt: str,
        system: str = "",
        json_mode: bool = False,
        temperature: float | None = None,
    ) -> LLMResponse:
        """Return a completion for *prompt*."""

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Return one embedding vector per input text."""
