"""The deterministic planner is the offline floor; it has to be dependable."""

from __future__ import annotations

import pytest

from forkable_ai_agent.agent.planner import Planner, extract_json
from forkable_ai_agent.llm.rules import RuleBasedLLM, nl_to_plan_dict
from forkable_ai_agent.schema import PlanError, TestPlan

SPEC = """Test: login_happy_path
go to the login page
fill username with demo
fill password with secret123
click log in
should be redirected to /dashboard
should see Welcome
"""


def test_rule_grammar_produces_expected_actions():
    plan = TestPlan.from_dict(nl_to_plan_dict(SPEC))
    assert plan.name == "login_happy_path"
    assert [s.action for s in plan.steps] == [
        "goto", "fill", "fill", "click", "expect_url", "expect_text",
    ]
    assert plan.steps[0].target == "/login"
    assert plan.steps[1].value == "demo"
    assert plan.steps[4].value == "/dashboard"


def test_login_shorthand_expands_to_three_steps():
    plan = TestPlan.from_dict(nl_to_plan_dict(
        "go to /login\nlog in with username demo and password secret123"
    ))
    actions = [(s.action, s.target, s.value) for s in plan.steps]
    assert ("fill", "username", "demo") in actions
    assert ("fill", "password", "secret123") in actions
    assert actions[-1][0] == "click"


@pytest.mark.parametrize("sentence,action", [
    ("open the dashboard", "goto"),
    ("click the submit button", "click"),
    ("check the remember me checkbox", "check"),
    ("select Europe from the region dropdown", "select"),
    ("the title should be Forkable Ops", "expect_title"),
    ("should not see Invalid", "expect_no_text"),
    ("take a screenshot", "screenshot"),
    ("wait 2 seconds", "wait"),
])
def test_grammar_covers_common_phrasings(sentence, action):
    plan = TestPlan.from_dict(nl_to_plan_dict(f"go to /login\n{sentence}"))
    assert plan.steps[-1].action == action


def test_unparseable_spec_raises(settings):
    with pytest.raises(PlanError):
        Planner(settings, RuleBasedLLM()).plan("colourless green ideas sleep furiously")


def test_planner_falls_back_when_model_returns_garbage(settings):
    class BadModel:
        name = "ollama"

        def generate(self, *a, **k):
            from forkable_ai_agent.llm.base import LLMResponse
            return LLMResponse(text="I'm afraid I can't do that")

    planner = Planner(settings, BadModel())
    plan = planner.plan(SPEC)
    assert plan.source == "rules"
    assert any("rule engine" in w for w in planner.warnings)


def test_planner_accepts_valid_model_json(settings):
    class GoodModel:
        name = "ollama"

        def generate(self, *a, **k):
            from forkable_ai_agent.llm.base import LLMResponse
            return LLMResponse(text='```json\n{"name":"m","steps":[{"action":"goto","target":"/"}]}\n```')

    plan = Planner(settings, GoodModel()).plan(SPEC)
    assert plan.source == "llm" and plan.steps[0].action == "goto"


def test_extract_json_unwraps_fences_and_prose():
    assert extract_json('sure!\n```json\n{"a": 1}\n```') == '{"a": 1}'


def test_invalid_action_is_rejected():
    with pytest.raises(PlanError):
        TestPlan.from_dict({"name": "x", "steps": [{"action": "teleport"}]})
