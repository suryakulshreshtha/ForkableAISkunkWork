"""A stand-in Ollama daemon.

The agent's LLM path was the least-proven surface: no daemon exists in CI or on
a fresh clone, so every model-driven branch — plan generation, the healing
tie-break, embeddings, failure narration, model resolution — went untested.

This serves the real endpoints (``/api/tags``, ``/api/generate``,
``/api/embed``, ``/api/embeddings``) with the real payload shapes on loopback,
so the client is exercised over actual HTTP rather than against a mock object.
It does not pretend to be a language model: responses are scripted per task
marker, which is what makes the assertions deterministic.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


class FakeOllama:
    """Scriptable Ollama-compatible server bound to 127.0.0.1."""

    def __init__(
        self,
        models: list[str] | None = None,
        responder: Callable[[dict], str] | None = None,
        embed_dim: int = 8,
        fail_generate: bool = False,
    ) -> None:
        self.models = models if models is not None else ["qwen2.5-coder:14b", "nomic-embed-text"]
        self.responder = responder or (lambda payload: "{}")
        self.embed_dim = embed_dim
        self.fail_generate = fail_generate
        self.requests: list[dict[str, Any]] = []
        self.port = 0
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        server = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args: Any) -> None:
                return

            def _json(self, status: int, payload: dict) -> None:
                body = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:  # noqa: N802
                if self.path.startswith("/api/tags"):
                    self._json(200, {"models": [{"name": m} for m in server.models]})
                else:
                    self._json(404, {"error": "not found"})

            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length") or 0)
                payload = json.loads(self.rfile.read(length) or b"{}")
                server.requests.append({"path": self.path, "payload": payload})

                if self.path.startswith("/api/generate"):
                    if server.fail_generate:
                        self._json(500, {"error": "model crashed"})
                        return
                    self._json(200, {
                        "model": payload.get("model", "fake"),
                        "response": server.responder(payload),
                        "done": True,
                        "eval_count": 42,
                    })
                    return

                if self.path.startswith("/api/embed"):
                    # Newer batch endpoint. Deterministic pseudo-embeddings.
                    items = payload.get("input") or [payload.get("prompt", "")]
                    vectors = [server._vector(text) for text in items]
                    if self.path.startswith("/api/embeddings"):
                        self._json(200, {"embedding": vectors[0]})
                    else:
                        self._json(200, {"embeddings": vectors})
                    return

                self._json(404, {"error": "not found"})

        return Handler

    def _vector(self, text: str) -> list[float]:
        seed = sum(ord(c) * (i + 1) for i, c in enumerate(str(text)))
        return [((seed >> (i % 16)) % 97) / 97.0 for i in range(self.embed_dim)]

    def start(self) -> FakeOllama:
        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.port = self._httpd.server_address[1]
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._httpd = self._thread = None

    def __enter__(self) -> FakeOllama:
        return self.start()

    def __exit__(self, *exc: object) -> None:
        self.stop()
