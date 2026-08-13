"""Locator memory: scoring, persistence and reporting."""

from __future__ import annotations

from forkable_ai_agent.agent.memory import Memory, scope_for


def test_scope_ignores_host_port_and_query():
    assert scope_for("http://127.0.0.1:8799/login?ui=v2") == "/login"
    assert scope_for("http://localhost:9000/login") == "/login"
    assert scope_for("") == "*"


def test_successes_outrank_failures(tmp_path):
    memory = Memory(tmp_path / "m.json")
    memory.record_success("login", "/login", "css||0|#good", "id")
    memory.record_success("login", "/login", "css||0|#good", "id")
    memory.record_success("login", "/login", "css||0|#meh", "id")
    memory.record_failure("login", "/login", "css||0|#meh")
    memory.record_failure("login", "/login", "css||0|#meh")

    assert memory.known_keys("login", "/login")[0] == "css||0|#good"


def test_round_trips_through_disk(tmp_path):
    path = tmp_path / "m.json"
    first = Memory(path)
    first.record_success("username", "/login", "testid||0|[data-testid=\"u\"]", "data-testid", healed=True)
    first.record_run({"name": "login", "status": "passed"})
    first.save()

    second = Memory(path)
    assert second.known_keys("username", "/login") == ['testid||0|[data-testid="u"]']
    assert second.runs[-1]["status"] == "passed"


def test_healing_report_surfaces_healed_entries_first(tmp_path):
    memory = Memory(tmp_path / "m.json")
    memory.record_success("plain", "/a", "css||0|#p", "id")
    memory.record_success("fixed", "/a", "css||0|#f", "healed-id", healed=True)
    assert memory.healing_report()[0]["description"] == "fixed"


def test_unknown_description_returns_nothing(tmp_path):
    assert Memory(tmp_path / "m.json").known_keys("nope", "/x") == []
