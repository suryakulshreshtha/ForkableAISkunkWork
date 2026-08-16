"""Configuration for PlaywrightSelfHealer.

Precedence (lowest to highest): dataclass defaults -> config/agent.toml -> env vars.
TOML is read with the stdlib ``tomllib`` (Python 3.11+) so config parsing adds
zero third-party dependencies and works with no network.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - only on <3.11
    tomllib = None  # type: ignore[assignment]


def project_root() -> Path:
    """Root of the PlaywrightSelfHealer project (the folder holding pyproject.toml)."""
    return Path(__file__).resolve().parents[2]


def _as_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class LLMConfig:
    """Local LLM settings. ``base_url`` must stay on loopback."""

    provider: str = "ollama"          # ollama | none
    base_url: str = "http://127.0.0.1:11434"
    model: str = "qwen2.5-coder:14b"
    embed_model: str = "nomic-embed-text"
    # Tried in order when `model` is not present in `ollama list`. Ordered to
    # match the models already pulled for the sibling ForkedUpAIExperiments
    # projects, so a shared box needs no extra downloads.
    model_preferences: list[str] = field(default_factory=lambda: [
        "qwen2.5-coder:14b", "qwen2.5-coder:7b", "qwen3:8b", "qwen2.5:7b",
        "llama3.1:8b", "llama3:8b", "mistral:7b", "phi3:mini",
    ])
    embed_preferences: list[str] = field(default_factory=lambda: [
        "nomic-embed-text", "mxbai-embed-large", "all-minilm",
    ])
    temperature: float = 0.1
    timeout_s: float = 120.0
    num_ctx: int = 8192
    # When the daemon is missing, fall back to the deterministic rule engine
    # instead of raising. This is what keeps the agent usable with zero LLM.
    allow_rule_based_fallback: bool = True


@dataclass
class RAGConfig:
    knowledge_dir: str = "knowledge"
    index_dir: str = ".forkable/index"
    chunk_chars: int = 900
    chunk_overlap: int = 150
    top_k: int = 5
    hybrid_alpha: float = 0.6          # 1.0 = pure dense, 0.0 = pure BM25
    embed_dim: int = 512               # used by the offline hashing embedder
    embedder: str = "auto"             # auto | ollama | hashing
    backend: str = "builtin"           # builtin | chroma (chroma is an optional extra)


@dataclass
class BrowserConfig:
    engine: str = "chromium"           # chromium | firefox | webkit
    headless: bool = True
    slow_mo_ms: int = 0
    viewport_width: int = 1280
    viewport_height: int = 800
    default_timeout_ms: int = 5000
    trace: bool = False
    artifacts_dir: str = ".forkable/artifacts"


@dataclass
class AppConfig:
    """The bundled demo target that makes end-to-end runs possible offline."""

    host: str = "127.0.0.1"
    port: int = 8799

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"


@dataclass
class VisualConfig:
    baseline_dir: str = "baselines"
    diff_dir: str = ".forkable/artifacts/visual"
    pixel_tolerance: int = 12          # per-channel delta treated as noise
    max_diff_ratio: float = 0.02       # fail above 2% changed pixels


@dataclass
class Settings:
    offline: bool = True               # hard-block non-loopback sockets
    llm: LLMConfig = field(default_factory=LLMConfig)
    rag: RAGConfig = field(default_factory=RAGConfig)
    browser: BrowserConfig = field(default_factory=BrowserConfig)
    app: AppConfig = field(default_factory=AppConfig)
    visual: VisualConfig = field(default_factory=VisualConfig)
    memory_path: str = ".forkable/memory.json"
    # Prefixed onto every locator-memory scope. Two environments that serve
    # different DOMs at the same path (staging vs prod, or the demo's v1 vs v2)
    # must not share learned selectors.
    memory_namespace: str = ""
    report_dir: str = ".forkable/reports"
    root: str = ""

    # ---- path helpers -------------------------------------------------
    def path(self, relative: str) -> Path:
        p = Path(relative)
        return p if p.is_absolute() else Path(self.root or project_root()) / p

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _apply_table(obj: Any, table: dict[str, Any]) -> None:
    for key, value in table.items():
        if not hasattr(obj, key):
            continue
        current = getattr(obj, key)
        if hasattr(current, "__dataclass_fields__") and isinstance(value, dict):
            _apply_table(current, value)
        else:
            setattr(obj, key, value)


def load_settings(config_path: str | os.PathLike[str] | None = None) -> Settings:
    """Build a :class:`Settings` from file + environment."""
    root = project_root()
    settings = Settings(root=str(root))

    path = Path(config_path) if config_path else root / "config" / "agent.toml"
    if path.exists() and tomllib is not None:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
        _apply_table(settings, data)

    env = os.environ
    settings.offline = _as_bool(env.get("FORKABLE_OFFLINE"), settings.offline)
    settings.llm.base_url = env.get("OLLAMA_HOST", settings.llm.base_url)
    settings.llm.model = env.get("FORKABLE_LLM_MODEL", settings.llm.model)
    settings.llm.embed_model = env.get("FORKABLE_EMBED_MODEL", settings.llm.embed_model)
    settings.llm.provider = env.get("FORKABLE_LLM_PROVIDER", settings.llm.provider)
    settings.rag.embedder = env.get("FORKABLE_EMBEDDER", settings.rag.embedder)
    settings.browser.engine = env.get("FORKABLE_BROWSER", settings.browser.engine)
    settings.browser.headless = _as_bool(
        env.get("FORKABLE_HEADLESS"), settings.browser.headless
    )
    settings.memory_namespace = env.get("FORKABLE_MEMORY_NS", settings.memory_namespace)
    if env.get("FORKABLE_APP_PORT"):
        settings.app.port = int(env["FORKABLE_APP_PORT"])

    if not settings.llm.base_url.startswith("http"):
        settings.llm.base_url = "http://" + settings.llm.base_url
    return settings
