"""The Ollama path, exercised over real HTTP against a scripted daemon."""

from __future__ import annotations

import json

import pytest

from forkable_ai_agent.agent.healer import LocatorResolver
from forkable_ai_agent.agent.memory import Memory
from forkable_ai_agent.agent.planner import Planner
from forkable_ai_agent.llm import OllamaLLM, build_llm
from forkable_ai_agent.llm.base import LLMUnavailable
from forkable_ai_agent.rag import KnowledgeBase
from tests.support.fake_ollama import FakeOllama
from tests.support.fake_page import FakePage

PLAN_JSON = json.dumps({
    "name": "model_authored",
    "steps": [
        {"action": "goto", "target": "/login"},
        {"action": "fill", "target": "username", "value": "demo"},
        {"action": "click", "target": "log in"},
    ],
})


@pytest.fixture
def ollama():
    server = FakeOllama().start()
    yield server
    server.stop()


@pytest.fixture
def ollama_settings(settings, ollama):
    """Settings pointed at the fake daemon.

    CI exports FORKABLE_LLM_PROVIDER=none to force the deterministic engine, so
    tests that are specifically about the model path have to opt back in rather
    than inherit whatever the environment says.
    """
    settings.llm.provider = "ollama"
    settings.llm.base_url = ollama.base_url
    return settings


def _client(server, **kw):
    return OllamaLLM(base_url=server.base_url, **kw)


# -- client contract ----------------------------------------------------
def test_liveness_probe_and_model_listing(ollama):
    client = _client(ollama)
    assert client.available()
    assert "qwen2.5-coder:14b" in client.list_models()


def test_dead_daemon_reports_unavailable():
    client = OllamaLLM(base_url="http://127.0.0.1:1")  # nothing listening
    assert client.available() is False


def test_non_loopback_host_is_refused():
    with pytest.raises(ValueError, match="loopback"):
        OllamaLLM(base_url="http://api.openai.com")


def test_model_resolution_picks_what_is_actually_pulled():
    with FakeOllama(models=["qwen3:8b", "nomic-embed-text"]) as server:
        client = _client(server, model="qwen2.5-coder:14b")
        assert client.resolve_model(["qwen2.5-coder:14b", "qwen3:8b"]) == "qwen3:8b"


def test_model_resolution_matches_on_the_base_name():
    with FakeOllama(models=["qwen2.5-coder:32b"]) as server:
        client = _client(server, model="qwen2.5-coder:14b")
        assert client.resolve_model(["qwen2.5-coder:14b"]) == "qwen2.5-coder:32b"


def test_generate_sends_the_expected_payload(ollama):
    ollama.responder = lambda payload: "hello"
    client = _client(ollama, model="qwen2.5-coder:14b", temperature=0.3)
    response = client.generate("prompt text", system="be brief", json_mode=True)

    assert response.text == "hello"
    sent = ollama.requests[-1]["payload"]
    assert sent["model"] == "qwen2.5-coder:14b"
    assert sent["stream"] is False
    assert sent["format"] == "json"
    assert sent["system"] == "be brief"
    assert sent["options"]["temperature"] == 0.3


def test_server_error_raises_llm_unavailable(ollama):
    ollama.fail_generate = True
    with pytest.raises(LLMUnavailable):
        _client(ollama).generate("anything")


def test_batch_and_single_embeddings(ollama):
    vectors = _client(ollama).embed(["alpha", "beta"])
    assert len(vectors) == 2 and len(vectors[0]) == 8
    assert vectors[0] != vectors[1]


# -- wired into the agent ----------------------------------------------
def test_build_llm_selects_ollama_and_resolves_the_model(ollama_settings, ollama):
    settings = ollama_settings
    settings.llm.model = "not-pulled:1b"
    client = build_llm(settings)
    assert client.name == "ollama"
    assert client.model == "qwen2.5-coder:14b"


def test_build_llm_falls_back_when_the_daemon_is_gone(settings):
    settings.llm.provider = "ollama"
    settings.llm.base_url = "http://127.0.0.1:1"
    assert build_llm(settings).name == "rules"


def test_planner_uses_a_model_authored_plan(ollama_settings, ollama):
    ollama.responder = lambda payload: PLAN_JSON
    settings = ollama_settings
    plan = Planner(settings, build_llm(settings)).plan("log in as demo")

    assert plan.source == "llm"
    assert plan.name == "model_authored"
    assert [s.action for s in plan.steps] == ["goto", "fill", "click"]
    assert "# task: plan" in ollama.requests[-1]["payload"]["prompt"]


def test_planner_retries_then_falls_back_on_bad_model_output(ollama_settings, ollama):
    ollama.responder = lambda payload: "not json at all"
    settings = ollama_settings
    planner = Planner(settings, build_llm(settings))
    plan = planner.plan("go to the login page\nclick log in")

    assert plan.source == "rules"
    assert len(ollama.requests) >= 2, "the planner should retry before giving up"
    assert any("invalid plan" in w for w in planner.warnings)


def test_healer_consults_the_model_only_when_heuristics_are_weak(
    ollama_settings, demo_app, variant_v2, ollama
):
    """The model is a tie-breaker, not the mechanism."""
    ollama.responder = lambda payload: json.dumps(
        {"index": 0, "confidence": 0.9, "reason": "scripted"}
    )
    settings = ollama_settings
    page = FakePage(demo_app.base_url)
    page.goto("/login")

    resolver = LocatorResolver(settings, Memory(settings.path(settings.memory_path)),
                               llm=build_llm(settings))
    resolution = resolver.resolve(page, "username", "fill")

    assert resolution.healed
    generate_calls = [r for r in ollama.requests if r["path"].startswith("/api/generate")]
    if generate_calls:
        assert "# task: heal" in generate_calls[-1]["payload"]["prompt"]
        assert resolver.events[-1]["source"] in {"llm", "heuristic"}
    else:
        # the heuristic scored highly enough that no model call was needed
        assert resolver.events[-1]["source"] == "heuristic"


def test_a_dead_model_never_breaks_healing(ollama_settings, demo_app, variant_v2, ollama):
    ollama.fail_generate = True
    settings = ollama_settings
    page = FakePage(demo_app.base_url)
    page.goto("/login")
    resolver = LocatorResolver(settings, Memory(settings.path(settings.memory_path)),
                               llm=build_llm(settings), ask_llm_below=1.0)

    resolution = resolver.resolve(page, "username", "fill")
    assert resolution.healed
    assert resolution.locator.nodes[0].get("id") == "usr_1a2b"


def test_rag_uses_ollama_embeddings_when_available(ollama_settings, ollama):
    settings = ollama_settings
    settings.rag.embedder = "auto"
    kb = KnowledgeBase(settings, build_llm(settings))
    manifest = kb.index()

    assert manifest["embedder"] == "ollama"
    assert manifest["dim"] == 8
    assert any(r["path"].startswith("/api/embed") for r in ollama.requests)


def test_grounded_answer_uses_the_model(ollama_settings, ollama):
    ollama.responder = lambda payload: "Use data-testid first [1]."
    settings = ollama_settings
    kb = KnowledgeBase(settings, build_llm(settings))
    kb.index()
    answer, hits = kb.answer("which locator should I prefer?")

    assert "data-testid" in answer and hits
    assert "# task: qa" in ollama.requests[-1]["payload"]["prompt"]


def test_failure_analysis_uses_the_model(ollama_settings, ollama):
    from forkable_ai_agent.agent.analyzer import FailureAnalyzer

    ollama.responder = lambda payload: (
        "CAUSE: the id was renamed\nFIX: add a data-testid\nCONFIDENCE: 0.8"
    )
    settings = ollama_settings
    kb = KnowledgeBase(settings, build_llm(settings))
    kb.index()
    diagnosis = FailureAnalyzer(settings, kb, build_llm(settings)).analyze_text(
        "could not locate 'log in button'"
    )

    assert diagnosis.source == "llm"
    assert diagnosis.likely_cause == "the id was renamed"
    assert diagnosis.suggested_fix == "add a data-testid"
    assert diagnosis.confidence == 0.8
