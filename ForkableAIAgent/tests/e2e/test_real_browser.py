"""Real Chromium runs.

Skipped automatically when the browser bundle is absent, which is the normal
state on an air-gapped box before someone seeds PLAYWRIGHT_BROWSERS_PATH. The
rest of the suite covers the same logic through the DOM harness, so a skip here
is a gap in coverage of Playwright itself, not of the agent.
"""

from __future__ import annotations

import pytest

from forkable_ai_agent.browser import browsers_installed, playwright_installed

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(not playwright_installed(), reason="playwright package not installed"),
    pytest.mark.skipif(not browsers_installed("chromium"), reason="chromium bundle not installed"),
]

SPEC = """Test: login_happy_path
go to the login page
fill username with demo
fill password with secret123
click log in
should be redirected to /dashboard
should see Welcome
"""


def test_happy_path_in_chromium(settings, demo_app, variant_v1):
    from forkable_ai_agent.agent import ForkableAgent

    agent = ForkableAgent(settings, probe_llm=False)
    result = agent.run(SPEC, base_url=demo_app.base_url, autostart_app=False)
    assert result.status == "passed"
    assert result.healed_count == 0


def test_refactored_ui_is_healed_in_chromium(settings, demo_app, variant_v2):
    from forkable_ai_agent.agent import ForkableAgent

    agent = ForkableAgent(settings, probe_llm=False)
    result = agent.run(SPEC, base_url=demo_app.base_url, autostart_app=False)
    assert result.status == "passed"
    assert result.healed_count >= 1


def test_visual_baseline_round_trip(settings, demo_app, variant_v1):
    from forkable_ai_agent.browser import BrowserSession
    from forkable_ai_agent.visual import VisualValidator

    validator = VisualValidator(settings)
    with BrowserSession(settings) as session:
        session.page.goto(f"{demo_app.base_url}/login")
        first = validator.check(session.page, "login_page")
        assert first.created_baseline
        second = validator.check(session.page, "login_page")
        assert second.passed and not second.created_baseline
