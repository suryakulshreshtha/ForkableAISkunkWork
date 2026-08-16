"""API steps, and the UI-then-API session sharing that makes them worth having."""

from __future__ import annotations

import pytest

from forkable_ai_agent.agent.executor import Executor
from forkable_ai_agent.agent.healer import LocatorResolver
from forkable_ai_agent.agent.memory import Memory
from forkable_ai_agent.agent.planner import Planner
from forkable_ai_agent.schema import PlanError, Step
from tests.support.fake_page import FakeSession

UI_THEN_API = """Test: api_after_ui_login
go to the login page
fill username with demo
fill password with secret123
click log in
call GET /api/jobs
the response status should be 200
jobs.0.name should be nightly-ingest
the response count should be 3
"""


def _run(settings, demo_app, spec):
    plan = Planner(settings, None).plan(spec, demo_app.base_url)
    executor = Executor(settings, LocatorResolver(settings, Memory(settings.path(settings.memory_path))))
    return executor.run(plan, FakeSession(demo_app.base_url))


def test_api_request_target_is_validated():
    Step(action="api_request", target="get /api/jobs")   # normalised to upper
    with pytest.raises(PlanError):
        Step(action="api_request", target="/api/jobs")
    with pytest.raises(PlanError):
        Step(action="api_request", target="FETCH /api/jobs")


def test_grammar_parses_api_phrasings(settings, demo_app):
    plan = Planner(settings, None).plan(UI_THEN_API, demo_app.base_url)
    assert [s.action for s in plan.steps[-4:]] == [
        "api_request", "expect_status", "expect_json", "expect_json",
    ]
    assert plan.steps[-4].target == "GET /api/jobs"


def test_ui_login_authenticates_the_api_call(settings, demo_app, variant_v1):
    """The whole point: one session, not two."""
    result = _run(settings, demo_app, UI_THEN_API)
    assert result.status == "passed", [s.message for s in result.steps if s.status == "failed"]
    assert result.steps[-4].message == "HTTP 200"


def test_api_without_login_is_rejected(settings, demo_app):
    spec = "call GET /api/jobs\nthe response status should be 200"
    result = _run(settings, demo_app, spec)
    assert result.status == "failed"
    assert "expected status 200, got 401" in result.steps[-1].message


def test_post_with_a_json_body(settings, demo_app):
    spec = (
        'call POST /api/login with {"username": "demo", "password": "secret123"}\n'
        "the response status should be 200\n"
        "the response user should be demo\n"
    )
    assert _run(settings, demo_app, spec).status == "passed"


def test_bad_credentials_return_401(settings, demo_app):
    spec = (
        'call POST /api/login with {"username": "demo", "password": "nope"}\n'
        "the response status should be 401\n"
        "the response error should contain invalid\n"
    )
    assert _run(settings, demo_app, spec).status == "passed"


def test_missing_json_path_fails_clearly(settings, demo_app, variant_v1):
    spec = UI_THEN_API.replace("jobs.0.name should be nightly-ingest", "jobs.0.nope should be x")
    result = _run(settings, demo_app, spec)
    assert result.status == "failed"
    assert "no key 'nope'" in result.steps[-1].message


def test_assertion_before_a_request_is_rejected(settings, demo_app):
    result = _run(settings, demo_app, "the response status should be 200")
    assert result.status == "failed"
    assert "needs an api_request step before it" in result.steps[-1].message
