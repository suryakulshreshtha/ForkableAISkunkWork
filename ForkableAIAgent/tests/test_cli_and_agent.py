"""CLI surface and the ForkableAgent façade."""

from __future__ import annotations

import json

import pytest

from forkable_ai_agent.agent import ForkableAgent, port_open
from forkable_ai_agent.cli import build_parser, main

SPEC = "go to the login page\nfill username with demo\nclick log in"


def test_parser_exposes_every_command():
    parser = build_parser()
    for command in ["doctor", "serve", "index", "ask", "plan", "generate", "run", "heal-report", "demo"]:
        assert parser.parse_args([command] + (["q"] if command == "ask" else []))


def test_plan_command_emits_json(capsys):
    assert main(["plan", SPEC, "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["steps"][0]["action"] == "goto"


def test_generate_command_writes_a_file(tmp_path, capsys):
    assert main(["generate", SPEC, "--out", str(tmp_path)]) == 0
    written = list(tmp_path.glob("test_*.py"))
    assert written and "playwright" in written[0].read_text()


def test_doctor_reports_without_crashing(capsys):
    main(["doctor"])
    out = capsys.readouterr().out
    assert "offline guard" in out and "ollama daemon" in out


def test_unknown_command_exits_nonzero():
    with pytest.raises(SystemExit):
        main(["nonsense"])


def test_agent_starts_and_stops_the_demo_app(settings):
    settings.app.port = 8919
    agent = ForkableAgent(settings, probe_llm=False)
    assert agent.ensure_app() is True
    assert port_open("127.0.0.1", 8919)
    agent.stop_app()


def test_agent_doctor_flags_missing_browsers(settings):
    checks = {c.name: c for c in ForkableAgent(settings, probe_llm=False).doctor()}
    assert "browser binaries" in checks
    assert checks["ollama daemon"].required is False


def test_agent_falls_back_to_the_rule_engine_without_ollama(settings):
    agent = ForkableAgent(settings)
    assert agent.llm.name == "rules"
    assert agent.plan(SPEC).source == "rules"
