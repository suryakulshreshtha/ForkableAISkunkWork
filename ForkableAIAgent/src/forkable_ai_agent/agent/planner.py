"""Natural language -> validated :class:`TestPlan`.

Two paths, one contract. A local model produces plan JSON; the deterministic
rule grammar produces the same JSON when no model is loaded or when the model
returns something that fails validation. Everything downstream - execution,
codegen, reporting - only ever sees a validated plan, so plan quality problems
never leak into the browser layer.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from typing import Any

from ..llm.rules import nl_to_plan_dict
from ..schema import ACTIONS, PlanError, TestPlan

PLAN_SYSTEM = (
    "You convert plain-English UI test descriptions into a JSON test plan for "
    "Playwright. Reply with JSON only - no prose, no markdown fences.\n"
    "Schema: {\"name\": str, \"description\": str, \"steps\": "
    "[{\"action\": str, \"target\": str, \"value\": str, \"optional\": bool}]}\n"
    f"Allowed actions: {', '.join(sorted(ACTIONS))}.\n"
    "Rules:\n"
    "- 'target' is a HUMAN description of the element ('password field', 'log in button'), "
    "never a CSS selector or XPath. The runtime resolves and heals selectors itself.\n"
    "- For 'goto', 'target' is a path such as /login.\n"
    "- For expect_url / expect_text / expect_title / expect_no_text, put the expected "
    "string in 'value' and leave 'target' empty.\n"
    "- Keep the plan minimal: one user-visible action per step.\n"
    "- Use snake_case for 'name'."
)

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)
_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def extract_json(text: str) -> str:
    """Pull a JSON object out of a model reply that may be wrapped in prose."""
    if not text:
        return ""
    fenced = _FENCE_RE.search(text)
    if fenced:
        text = fenced.group(1)
    match = _OBJECT_RE.search(text)
    return match.group(0) if match else text.strip()


class Planner:
    def __init__(self, settings, llm: Any = None) -> None:
        self.settings = settings
        self.llm = llm
        self.warnings: list[str] = []

    # ------------------------------------------------------------------
    def _prompt(self, spec: str, base_url: str, error: str = "") -> str:
        parts = [
            "# task: plan",
            f"Base URL: {base_url or self.settings.app.base_url}",
            "Convert this specification into plan JSON.",
            "<<<SPEC",
            spec.strip(),
            "SPEC>>>",
        ]
        if error:
            parts.append(f"The previous attempt was rejected: {error}. Fix it and reply with JSON only.")
        return "\n".join(parts)

    def _rules_plan(self, spec: str, base_url: str) -> TestPlan:
        try:
            data = nl_to_plan_dict(spec, base_url=base_url)
        except ValueError as exc:
            # Callers only ever have to catch PlanError.
            raise PlanError(str(exc)) from exc
        plan = TestPlan.from_dict(data)
        plan.source = "rules"
        return plan

    # ------------------------------------------------------------------
    def plan(self, spec: str, base_url: str = "", retries: int = 1) -> TestPlan:
        base = base_url or self.settings.app.base_url
        spec = (spec or "").strip()
        if not spec:
            raise PlanError("empty specification")

        if self.llm is None or getattr(self.llm, "name", "") == "rules":
            return self._rules_plan(spec, base)

        error = ""
        for _ in range(max(1, retries + 1)):
            try:
                response = self.llm.generate(
                    self._prompt(spec, base, error), system=PLAN_SYSTEM, json_mode=True
                )
            except Exception as exc:
                self.warnings.append(f"model call failed ({exc}); using rule engine")
                break
            try:
                data = json.loads(extract_json(response.text))
                if isinstance(data, dict) and data.get("error"):
                    raise PlanError(str(data["error"]))
                data.setdefault("base_url", base)
                plan = TestPlan.from_dict(data)
                plan.source = "llm"
                return plan
            except (PlanError, json.JSONDecodeError, AttributeError) as exc:
                error = str(exc)[:200]
                self.warnings.append(f"model produced an invalid plan: {error}")

        try:
            plan = self._rules_plan(spec, base)
            self.warnings.append("fell back to the deterministic rule engine")
            return plan
        except ValueError as exc:
            raise PlanError(
                f"neither the model nor the rule engine could plan this spec: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    def plan_many(self, specs: Sequence[str], base_url: str = "") -> list[TestPlan]:
        return [self.plan(spec, base_url) for spec in specs]

    def load_plan(self, path: str) -> TestPlan:
        from pathlib import Path

        text = Path(path).read_text(encoding="utf-8")
        if path.endswith(".json"):
            plan = TestPlan.from_json(text)
            plan.source = "file"
            return plan
        return self.plan(text)
