"""Plan execution.

Each step is resolved (with healing), acted on, timed and recorded. Failures
capture a screenshot and stop the run unless the step is marked optional. The
executor deliberately implements its own polling assertions rather than using
``expect`` so that every wait, retry and message is reportable data rather than
a raised exception with an opaque string.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any
from urllib.parse import urljoin

from ..schema import ELEMENT_ACTIONS, RunResult, Step, StepResult, TestPlan
from .healer import LocatorResolver


class StepFailed(RuntimeError):
    pass


def _poll(check: Callable[[], bool], timeout_ms: int, interval_ms: int = 100) -> bool:
    deadline = time.time() + timeout_ms / 1000.0
    while True:
        try:
            if check():
                return True
        except Exception:
            pass
        if time.time() >= deadline:
            return False
        time.sleep(interval_ms / 1000.0)


class Executor:
    def __init__(
        self,
        settings,
        resolver: LocatorResolver,
        analyzer: Any = None,
        visual: Any = None,
        on_step: Callable[[StepResult], None] | None = None,
    ) -> None:
        self.settings = settings
        self.resolver = resolver
        self.analyzer = analyzer
        self.visual = visual
        self.on_step = on_step

    # ------------------------------------------------------------------
    def _url_for(self, plan: TestPlan, target: str) -> str:
        base = plan.base_url or self.settings.app.base_url
        if target.startswith(("http://", "https://")):
            return target
        return urljoin(base.rstrip("/") + "/", target.lstrip("/"))

    # ------------------------------------------------------------------
    def run(self, plan: TestPlan, session: Any) -> RunResult:
        page = session.page
        result = RunResult(plan=plan)
        timeout = self.settings.browser.default_timeout_ms

        for index, step in enumerate(plan.steps, start=1):
            started = time.perf_counter()
            record = StepResult(index=index, step=step)
            try:
                self._execute(plan, page, session, step, record, timeout)
                record.status = "passed"
            except Exception as exc:
                record.message = f"{type(exc).__name__}: {exc}"
                record.status = "warned" if step.optional else "failed"
                record.screenshot = session.screenshot(f"fail_step_{index}")
            record.duration_ms = round((time.perf_counter() - started) * 1000, 1)
            result.steps.append(record)
            if self.on_step:
                self.on_step(record)
            if record.status == "failed":
                result.status = "failed"
                break

        result.finished_at = time.time()
        if result.status != "failed":
            result.status = "passed"
        if result.status == "failed" and self.analyzer is not None:
            result.diagnosis = self.analyzer.analyze_run(result)
        return result

    # ------------------------------------------------------------------
    def _execute(
        self,
        plan: TestPlan,
        page: Any,
        session: Any,
        step: Step,
        record: StepResult,
        timeout: int,
    ) -> None:
        action = step.action

        if action == "goto":
            page.goto(self._url_for(plan, step.target or "/"), wait_until="domcontentloaded")
            record.selector = self._url_for(plan, step.target or "/")
            return

        if action == "wait":
            seconds = float(step.value or "1")
            time.sleep(min(seconds if seconds < 100 else seconds / 1000.0, 30.0))
            return

        if action == "screenshot":
            record.screenshot = session.screenshot(step.value or f"step_{record.index}")
            return

        if action == "visual_check":
            if self.visual is None:
                record.message = "visual comparison unavailable (Pillow not installed)"
                record.status = "warned"
                return
            name = step.value or f"{plan.name}_{record.index}"
            outcome = self.visual.check(page, name)
            record.message = outcome.summary
            record.screenshot = outcome.diff_path or outcome.actual_path
            if not outcome.passed:
                raise StepFailed(f"visual diff {outcome.summary}")
            return

        if action == "expect_url":
            expected = step.value
            if not _poll(lambda: expected in (page.url or ""), timeout):
                raise StepFailed(f"expected url to contain {expected!r}, got {page.url!r}")
            record.selector = page.url
            return

        if action == "expect_title":
            expected = step.value
            if not _poll(lambda: expected.lower() in (page.title() or "").lower(), timeout):
                raise StepFailed(f"expected title to contain {expected!r}, got {page.title()!r}")
            return

        if action in {"expect_text", "expect_no_text"}:
            expected = step.value
            want = action == "expect_text"

            def seen() -> bool:
                try:
                    body = page.inner_text("body")
                except Exception:
                    body = page.content()
                return (expected.lower() in (body or "").lower()) == want

            if not _poll(seen, timeout):
                verb = "expected text" if want else "expected NO text"
                raise StepFailed(f"{verb} {expected!r} on {page.url}")
            return

        # ---- element actions -----------------------------------------
        if action in ELEMENT_ACTIONS:
            resolution = self.resolver.resolve(page, step.target, action)
            record.selector = resolution.candidate.describe()
            record.strategy = resolution.strategy
            record.healed = resolution.healed
            locator = resolution.locator

            if action == "click":
                locator.click(timeout=timeout)
            elif action == "fill":
                locator.fill(step.value or "", timeout=timeout)
            elif action == "press":
                locator.press(step.value or "Enter", timeout=timeout)
            elif action == "check":
                locator.check(timeout=timeout)
            elif action == "uncheck":
                locator.uncheck(timeout=timeout)
            elif action == "hover":
                locator.hover(timeout=timeout)
            elif action == "select":
                locator.select_option(step.value, timeout=timeout)
            elif action == "expect_visible":
                if not locator.is_visible():
                    raise StepFailed(f"{step.target!r} is not visible")
            elif action == "expect_value":
                actual = locator.input_value(timeout=timeout)
                if step.value.lower() not in (actual or "").lower():
                    raise StepFailed(f"expected value {step.value!r}, got {actual!r}")
            return

        raise StepFailed(f"unsupported action {action!r}")
