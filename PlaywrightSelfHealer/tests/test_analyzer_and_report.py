"""Failure classification, RAG-grounded diagnosis and the offline report."""

from __future__ import annotations

import pytest

from forkable_ai_agent.agent.analyzer import FailureAnalyzer, classify
from forkable_ai_agent.rag import KnowledgeBase
from forkable_ai_agent.reporting import render_html, write_report
from forkable_ai_agent.schema import RunResult, Step, StepResult, TestPlan


@pytest.mark.parametrize("text,expected", [
    ("could not locate 'log in button'", "selector_not_found"),
    ("Timeout 5000ms exceeded waiting for locator", "timeout"),
    ("net::ERR_CONNECTION_REFUSED at http://127.0.0.1:8799", "app_unreachable"),
    ("offline mode: refused connection to 'telemetry.example.com'", "offline_guard"),
    ("net::ERR_NAME_NOT_RESOLVED", "dns"),
    ("Executable doesn't exist at /root/.cache/ms-playwright", "browser_missing"),
    ("something entirely novel happened", "unknown"),
])
def test_classification_table(text, expected):
    assert classify(text)[0] == expected


def test_diagnosis_is_grounded_in_the_knowledge_base(settings):
    kb = KnowledgeBase(settings)
    kb.index()
    diagnosis = FailureAnalyzer(settings, kb).analyze_text(
        "could not locate 'log in button': no element matches"
    )
    assert diagnosis.category == "selector_not_found"
    assert diagnosis.citations, "the analyzer should cite local knowledge"
    assert diagnosis.suggested_fix
    assert diagnosis.source == "rules"


def _sample_result():
    plan = TestPlan(name="demo", base_url="http://127.0.0.1:8799", steps=[
        Step(action="goto", target="/login"),
        Step(action="click", target="log in"),
    ])
    result = RunResult(plan=plan, status="failed")
    result.steps = [
        StepResult(index=1, step=plan.steps[0], status="passed", duration_ms=12.0),
        StepResult(index=2, step=plan.steps[1], status="failed",
                   message="could not locate 'log in'", healed=True,
                   selector='testid([data-testid="login"])', strategy="healed-testid"),
    ]
    result.finished_at = result.started_at + 1.5
    return result


def test_report_is_self_contained(settings, tmp_path):
    result = _sample_result()
    html = render_html(result)
    assert "<script src=" not in html
    assert "http://" not in html.replace("http://127.0.0.1:8799", "")
    assert "healed" in html and "could not locate" in html


def test_report_files_are_written(settings):
    path = write_report(settings, _sample_result())
    assert path.exists()
    assert path.with_suffix(".json").exists()
    assert "PlaywrightSelfHealer run report" in path.read_text(encoding="utf-8")


def test_html_escapes_hostile_content(settings):
    result = _sample_result()
    result.steps[1].message = "<script>alert('xss')</script>"
    assert "<script>alert" not in render_html(result)
