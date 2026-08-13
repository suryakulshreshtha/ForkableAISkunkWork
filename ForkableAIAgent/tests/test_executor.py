"""Whole-plan execution against the demo app, on both UI variants."""

from __future__ import annotations

from forkable_ai_agent.agent.analyzer import FailureAnalyzer
from forkable_ai_agent.agent.executor import Executor
from forkable_ai_agent.agent.healer import LocatorResolver
from forkable_ai_agent.agent.memory import Memory
from forkable_ai_agent.agent.planner import Planner
from tests.support.fake_page import FakeSession

SPEC = """Test: login_happy_path
go to the login page
fill username with demo
fill password with secret123
click log in
should be redirected to /dashboard
should see Welcome
"""

BAD_SPEC = """Test: login_rejects_bad_password
go to the login page
fill username with demo
fill password with definitely-wrong
click log in
should see Invalid username or password
"""


def _run(settings, demo_app, spec):
    plan = Planner(settings, None).plan(spec, demo_app.base_url)
    memory = Memory(settings.path(settings.memory_path))
    resolver = LocatorResolver(settings, memory)
    executor = Executor(settings, resolver, FailureAnalyzer(settings))
    session = FakeSession(demo_app.base_url)
    return executor.run(plan, session), resolver, memory


def test_happy_path_passes_on_the_stable_ui(settings, demo_app, variant_v1):
    result, resolver, _ = _run(settings, demo_app, SPEC)
    assert result.status == "passed"
    assert [s.status for s in result.steps] == ["passed"] * 6
    assert result.healed_count == 0
    assert resolver.events == []


def test_same_plan_passes_on_the_refactored_ui_by_healing(settings, demo_app, variant_v2):
    result, resolver, memory = _run(settings, demo_app, SPEC)
    assert result.status == "passed", [s.message for s in result.steps if s.message]
    assert result.healed_count >= 1
    healed = [s for s in result.steps if s.healed]
    assert any(s.step.target == "username" for s in healed)
    assert memory.healing_report()


def test_negative_path_assertions_work(settings, demo_app, variant_v1):
    result, _, _ = _run(settings, demo_app, BAD_SPEC)
    assert result.status == "passed"


def test_failure_is_captured_and_diagnosed(settings, demo_app, variant_v1):
    spec = "go to the login page\nshould see Quarterly Revenue Forecast"
    result, _, _ = _run(settings, demo_app, spec)
    assert result.status == "failed"
    assert result.steps[-1].status == "failed"
    assert result.diagnosis is not None
    assert result.diagnosis.category in {"assertion_text", "unknown"}
    assert result.diagnosis.suggested_fix


def test_missing_element_is_diagnosed_as_selector_not_found(settings, demo_app, variant_v1):
    spec = "go to the login page\nclick the export to pdf button"
    result, _, _ = _run(settings, demo_app, spec)
    assert result.status == "failed"
    assert result.diagnosis.category == "selector_not_found"
    assert result.diagnosis.citations or result.diagnosis.suggested_fix


def test_optional_step_downgrades_to_a_warning(settings, demo_app, variant_v1):
    from forkable_ai_agent.schema import Step, TestPlan

    plan = TestPlan(
        name="optional_demo",
        base_url=demo_app.base_url,
        steps=[
            Step(action="goto", target="/login"),
            Step(action="click", target="dismiss cookie banner", optional=True),
            Step(action="expect_text", value="Sign in"),
        ],
    )
    memory = Memory(settings.path(settings.memory_path))
    executor = Executor(settings, LocatorResolver(settings, memory))
    result = executor.run(plan, FakeSession(demo_app.base_url))
    assert result.status == "passed"
    assert result.steps[1].status == "warned"


def test_second_run_reuses_learned_locators(settings, demo_app, variant_v2):
    first, _, memory = _run(settings, demo_app, SPEC)
    memory.save()
    assert first.status == "passed"

    second, resolver, _ = _run(settings, demo_app, SPEC)
    assert second.status == "passed"
    assert resolver.events == [], "the cache should make a second healing pass unnecessary"
    assert any(s.strategy == "memory-cache" for s in second.steps)
    assert second.healed_count == 0, "a cached locator is a hit, not a heal"
