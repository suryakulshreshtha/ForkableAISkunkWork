"""Ollama client built on ``urllib`` only - no ``requests``, no SDK, no wheels.

Ollama runs entirely on the machine, so this client is offline-safe by
construction: the base URL is validated to be loopback before any request.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Sequence
from typing import Any

from ..net_guard import is_loopback_host
from .base import LLMResponse, LLMUnavailable


class OllamaLLM:
    """Thin, dependency-free wrapper around the Ollama REST API."""

    name = "ollama"

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434",
        model: str = "qwen2.5-coder:7b",
        embed_model: str = "nomic-embed-text",
        temperature: float = 0.1,
        timeout_s: float = 120.0,
        num_ctx: int = 8192,
        enforce_loopback: bool = True,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.embed_model = embed_model
        self.temperature = temperature
        self.timeout_s = timeout_s
        self.num_ctx = num_ctx
        host = urllib.parse.urlparse(self.base_url).hostname
        if enforce_loopback and not is_loopback_host(host):
            raise ValueError(
                f"refusing non-loopback Ollama host {host!r}; "
                "PlaywrightSelfHealer keeps inference on the machine"
            )
        self._available: bool | None = None

    # ------------------------------------------------------------------
    def _post(self, path: str, payload: dict[str, Any], timeout: float | None = None) -> dict[str, Any]:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout or self.timeout_s) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _get(self, path: str, timeout: float = 2.0) -> dict[str, Any]:
        req = urllib.request.Request(f"{self.base_url}{path}", method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    # ------------------------------------------------------------------
    def available(self, refresh: bool = False) -> bool:
        if self._available is not None and not refresh:
            return self._available
        try:
            self._get("/api/tags", timeout=1.5)
            self._available = True
        except Exception:
            self._available = False
        return self._available

    def list_models(self) -> list[str]:
        try:
            payload = self._get("/api/tags", timeout=3.0)
        except Exception:
            return []
        return [m.get("name", "") for m in payload.get("models", []) if m.get("name")]

    # ------------------------------------------------------------------
    def resolve_model(self, preferences: Sequence[str] = ()) -> str:
        """Pick a model that is actually pulled locally.

        Nothing is more annoying than a 404 from the daemon because the config
        names a tag nobody downloaded. If the configured model is missing we
        walk the preference list, then fall back to whatever is installed.
        """
        installed = self.list_models()
        if not installed:
            return self.model
        names = {m.split(":")[0]: m for m in installed}
        if self.model in installed:
            return self.model
        for candidate in preferences:
            if candidate in installed:
                self.model = candidate
                return candidate
            base = candidate.split(":")[0]
            if base in names:
                self.model = names[base]
                return self.model
        self.model = installed[0]
        return self.model

    def resolve_embed_model(self, preferences: Sequence[str] = ()) -> str:
        installed = self.list_models()
        if not installed or self.embed_model in installed:
            return self.embed_model
        bases = {m.split(":")[0]: m for m in installed}
        for candidate in list(preferences) + [self.embed_model]:
            base = candidate.split(":")[0]
            if candidate in installed:
                self.embed_model = candidate
                return candidate
            if base in bases:
                self.embed_model = bases[base]
                return self.embed_model
        return self.embed_model

    def generate(
        self,
        prompt: str,
        system: str = "",
        json_mode: bool = False,
        temperature: float | None = None,
    ) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": self.temperature if temperature is None else temperature,
                "num_ctx": self.num_ctx,
            },
        }
        if system:
            payload["system"] = system
        if json_mode:
            payload["format"] = "json"

        started = time.perf_counter()
        try:
            data = self._post("/api/generate", payload)
        except urllib.error.URLError as exc:
            self._available = False
            raise LLMUnavailable(f"ollama unreachable at {self.base_url}: {exc}") from exc
        except Exception as exc:  # timeouts, malformed payloads
            raise LLMUnavailable(f"ollama request failed: {exc}") from exc

        latency = (time.perf_counter() - started) * 1000
        return LLMResponse(
            text=str(data.get("response", "")).strip(),
            model=str(data.get("model", self.model)),
            latency_ms=latency,
            meta={
                "eval_count": data.get("eval_count"),
                "total_duration": data.get("total_duration"),
            },
        )

    # ------------------------------------------------------------------
    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed with ``/api/embed`` (batch) falling back to ``/api/embeddings``."""
        items = list(texts)
        if not items:
            return []
        try:
            data = self._post(
                "/api/embed", {"model": self.embed_model, "input": items}, timeout=60.0
            )
            vectors = data.get("embeddings")
            if isinstance(vectors, list) and len(vectors) == len(items):
                return [[float(x) for x in vec] for vec in vectors]
        except Exception:
            pass  # older daemon: fall through to the single-item endpoint

        out: list[list[float]] = []
        for item in items:
            try:
                data = self._post(
                    "/api/embeddings",
                    {"model": self.embed_model, "prompt": item},
                    timeout=60.0,
                )
            except Exception as exc:
                raise LLMUnavailable(f"embedding failed: {exc}") from exc
            vec = data.get("embedding") or []
            out.append([float(x) for x in vec])
        return out
