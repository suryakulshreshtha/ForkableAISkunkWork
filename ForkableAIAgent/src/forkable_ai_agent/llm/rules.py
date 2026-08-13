"""Deterministic stand-in for a language model.

The agent must keep working on an air-gapped laptop where nobody has pulled an
Ollama model yet. This module turns plain-English test specs into the same
plan JSON an LLM would produce, using an ordered grammar of regular
expressions. It is not clever, but it is repeatable, instant and free - which
also makes it the ideal oracle in CI.

Prompts carry a ``# task: <name>`` marker on the first line and wrap the user
payload in ``<<<SPEC ... SPEC>>>``; that convention lets the same prompt string
drive either a real model or this engine.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from typing import Any

from .base import LLMResponse

SPEC_RE = re.compile(r"<<<SPEC\s*(.*?)\s*SPEC>>>", re.DOTALL)
TASK_RE = re.compile(r"#\s*task:\s*([a-z_]+)", re.IGNORECASE)

_PAGE_ALIASES = {
    "home": "/",
    "home page": "/",
    "landing": "/",
    "index": "/",
    "login": "/login",
    "login page": "/login",
    "sign in": "/login",
    "sign-in": "/login",
    "signin page": "/login",
    "dashboard": "/dashboard",
    "dashboard page": "/dashboard",
    "profile": "/profile",
    "settings": "/settings",
}

_FIELD_WORDS = r"(?:field|box|input|textbox|text box|control)"

# Ordered: the first pattern that matches a sentence wins.
_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("goto", re.compile(
        r"^(?:go to|open|navigate to|visit|browse to|land on)\s+(?P<target>.+?)\s*$",
        re.IGNORECASE)),
    ("wait", re.compile(
        r"^wait\s+(?:for\s+)?(?P<value>\d+(?:\.\d+)?)\s*(?:s|sec|secs|seconds?|ms)?\s*$",
        re.IGNORECASE)),
    ("screenshot", re.compile(
        r"^(?:take|capture|grab)\s+(?:a\s+)?screenshot(?:\s+(?:named|called)\s+(?P<value>\S+))?\s*$",
        re.IGNORECASE)),
    ("visual_check", re.compile(
        r"^(?:visual(?:ly)?\s+(?:check|compare|validate)|compare\s+(?:the\s+)?(?:page|screen))"
        r"(?:\s+(?:against|with|to)\s+(?P<value>\S+))?\s*$",
        re.IGNORECASE)),
    ("expect_url", re.compile(
        r"^(?:the\s+)?(?:url|address|page)\s+should\s+(?:be|contain|include|match)\s+(?P<value>.+?)\s*$",
        re.IGNORECASE)),
    ("expect_url", re.compile(
        r"^(?:should\s+)?(?:be\s+)?(?:redirect(?:ed)?|land|end\s+up|navigate)\s+(?:to|on)\s+(?P<value>.+?)\s*$",
        re.IGNORECASE)),
    ("expect_title", re.compile(
        r"^(?:the\s+)?title\s+should\s+(?:be|contain|include)\s+(?P<value>.+?)\s*$",
        re.IGNORECASE)),
    ("expect_no_text", re.compile(
        r"^(?:i\s+)?should\s+not\s+see\s+(?P<value>.+?)\s*$", re.IGNORECASE)),
    ("expect_visible", re.compile(
        r"^(?:the\s+)?(?P<target>.+?)\s+should\s+be\s+(?:visible|displayed|shown|present)\s*$",
        re.IGNORECASE)),
    ("expect_value", re.compile(
        r"^(?:the\s+)?(?P<target>.+?)\s+should\s+(?:contain|have)\s+(?:the\s+)?value\s+(?P<value>.+?)\s*$",
        re.IGNORECASE)),
    ("expect_text", re.compile(
        r"^(?:i\s+)?(?:should\s+see|expect\s+to\s+see|verify|assert|confirm|check\s+that\s+"
        r"(?:the\s+page\s+)?(?:shows|displays))\s+(?P<value>.+?)\s*$",
        re.IGNORECASE)),
    ("expect_text", re.compile(
        r"^(?:the\s+)?(?:page|screen)\s+(?:should\s+)?(?:shows?|displays?|contains?)\s+(?P<value>.+?)\s*$",
        re.IGNORECASE)),
    ("fill", re.compile(
        r"^(?:type|enter|fill|input|write)\s+(?P<value>.+?)\s+(?:in|into|in\s+the|to)\s+"
        r"(?:the\s+)?(?P<target>.+?)(?:\s+" + _FIELD_WORDS + r")?\s*$",
        re.IGNORECASE)),
    ("fill", re.compile(
        r"^(?:fill|set)\s+(?:in\s+|the\s+)?(?P<target>.+?)\s+(?:with|to|as)\s+(?P<value>.+?)\s*$",
        re.IGNORECASE)),
    ("select", re.compile(
        r"^(?:select|choose|pick)\s+(?P<value>.+?)\s+(?:from|in)\s+(?:the\s+)?(?P<target>.+?)\s*$",
        re.IGNORECASE)),
    ("check", re.compile(
        r"^(?:check|tick|enable)\s+(?:the\s+)?(?P<target>.+?)(?:\s+checkbox)?\s*$",
        re.IGNORECASE)),
    ("uncheck", re.compile(
        r"^(?:uncheck|untick|disable)\s+(?:the\s+)?(?P<target>.+?)(?:\s+checkbox)?\s*$",
        re.IGNORECASE)),
    ("hover", re.compile(
        r"^(?:hover|mouse)\s+(?:over\s+|on\s+)?(?:the\s+)?(?P<target>.+?)\s*$",
        re.IGNORECASE)),
    ("press", re.compile(
        r"^press\s+(?:the\s+)?(?P<value>enter|escape|tab|space|arrow\w+)\s+key"
        r"(?:\s+(?:in|on)\s+(?:the\s+)?(?P<target>.+?))?\s*$", re.IGNORECASE)),
    ("click", re.compile(
        r"^(?:click|press|tap|hit|submit|activate)\s+(?:on\s+)?(?:the\s+)?(?P<target>.+?)\s*$",
        re.IGNORECASE)),
]

# "log in with username demo and password secret" style shortcuts.
_CREDENTIAL_RE = re.compile(
    r"(?:with|using)\s+(?P<pairs>.+)$", re.IGNORECASE)
# The value is a single token or a quoted string. Anchoring to one token keeps
# "username demo and password secret" from swallowing the rest of the sentence.
_PAIR_RE = re.compile(
    r"(?P<field>username|user|email|password|passcode|pin)\s*(?:=|:)?\s*"
    r"(?:\"(?P<quoted>[^\"]+)\"|'(?P<single>[^']+)'|(?P<plain>[^\s\"',;]+))",
    re.IGNORECASE)


def _strip_wrapping(text: str) -> str:
    out = text.strip().strip(".;,")
    for quote in ('"', "'", "\u201c", "\u2018"):
        if out.startswith(quote):
            out = out[1:]
    for quote in ('"', "'", "\u201d", "\u2019"):
        if out.endswith(quote):
            out = out[:-1]
    return out.strip()


def _clean_target(text: str) -> str:
    out = _strip_wrapping(text).lower()
    out = re.sub(r"^(the|a|an)\s+", "", out)
    out = re.sub(r"\s+(button|link|field|box|input|checkbox|element|icon|tab|menu)$", "", out)
    return out.strip() or text.strip().lower()


def _normalise_url(text: str) -> str:
    raw = _strip_wrapping(text).lower()
    raw = re.sub(r"^(the|a|an)\s+", "", raw)
    raw = re.sub(r"\s+page$", " page", raw)
    if raw.startswith(("http://", "https://", "/")):
        return _strip_wrapping(text)
    if raw in _PAGE_ALIASES:
        return _PAGE_ALIASES[raw]
    key = raw.replace(" page", "").strip()
    if key in _PAGE_ALIASES:
        return _PAGE_ALIASES[key]
    slug = re.sub(r"[^a-z0-9]+", "-", key).strip("-")
    return f"/{slug}" if slug else "/"


def split_sentences(spec: str) -> list[str]:
    """Split a free-text spec into one instruction per element."""
    parts: list[str] = []
    for raw_line in spec.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        line = re.sub(r"^\s*(?:[-*\u2022]|\d+[.)])\s*", "", line)
        chunks = re.split(r"(?<=[.;])\s+|\s+then\s+|\s*->\s*|\s*\u2192\s*", line)
        for chunk in chunks:
            chunk = chunk.strip().strip(".;")
            if chunk:
                parts.append(chunk)
    return parts


def _credential_steps(sentence: str) -> list[dict[str, Any]]:
    match = _CREDENTIAL_RE.search(sentence)
    if not match:
        return []
    steps: list[dict[str, Any]] = []
    for pair in _PAIR_RE.finditer(match.group("pairs")):
        field = pair.group("field").lower()
        field = {"user": "username", "name": "username", "passcode": "password"}.get(field, field)
        value = pair.group("quoted") or pair.group("single") or pair.group("plain") or ""
        if value.lower() in {"and", "with", "the", "a"}:
            continue
        steps.append({"action": "fill", "target": field, "value": _strip_wrapping(value)})
    return steps


def nl_to_plan_dict(spec: str, base_url: str = "") -> dict[str, Any]:
    """Translate a natural-language spec into a plan dictionary."""
    sentences = split_sentences(spec)
    steps: list[dict[str, Any]] = []
    name_hint = ""

    for sentence in sentences:
        lowered = sentence.lower()
        if lowered.startswith(("test:", "scenario:", "name:", "feature:")):
            name_hint = sentence.split(":", 1)[1].strip()
            continue

        # "log in with username demo and password secret123"
        if re.match(r"^(?:log|sign)\s*(?:in|on)\b", lowered):
            creds = _credential_steps(sentence)
            if creds:
                steps.extend(creds)
                steps.append({"action": "click", "target": "log in"})
                continue

        matched = False
        for action, pattern in _RULES:
            match = pattern.match(sentence)
            if not match:
                continue
            groups = match.groupdict()
            target = groups.get("target") or ""
            value = groups.get("value") or ""
            step: dict[str, Any] = {"action": action}

            if action == "goto":
                step["target"] = _normalise_url(target)
            elif action in {"expect_url", "expect_title", "expect_text", "expect_no_text"}:
                step["value"] = (
                    _normalise_url(value) if action == "expect_url" else _strip_wrapping(value)
                )
            elif action == "wait":
                step["value"] = _strip_wrapping(value)
            elif action == "screenshot":
                step["value"] = _strip_wrapping(value) or f"step_{len(steps) + 1}"
            elif action == "visual_check":
                step["value"] = _strip_wrapping(value) or "page"
            else:
                step["target"] = _clean_target(target)
                if value:
                    step["value"] = _strip_wrapping(value)
                if action in {"click", "hover", "check", "uncheck"} and not step["target"]:
                    continue
            steps.append(step)
            matched = True
            break

        if not matched:
            creds = _credential_steps(sentence)
            if creds:
                steps.extend(creds)

    if not steps:
        raise ValueError(
            "could not derive any steps from the spec; use phrasing like "
            "'go to the login page', 'fill username with demo', 'click log in', "
            "'should see Welcome'"
        )

    name = name_hint or _derive_name(sentences)
    return {
        "name": name,
        "description": spec.strip().splitlines()[0][:200] if spec.strip() else "",
        "base_url": base_url,
        "steps": steps,
        "source": "rules",
    }


def _derive_name(sentences: Sequence[str]) -> str:
    for sentence in sentences:
        words = re.findall(r"[a-z0-9]+", sentence.lower())
        if words:
            return "_".join(words[:6])
    return "generated_test"


class RuleBasedLLM:
    """Implements the :class:`LLMClient` protocol without any model."""

    name = "rules"

    def __init__(self, embed_dim: int = 512) -> None:
        self.embed_dim = embed_dim

    def available(self) -> bool:
        return True

    def generate(
        self,
        prompt: str,
        system: str = "",
        json_mode: bool = False,
        temperature: float | None = None,
    ) -> LLMResponse:
        task_match = TASK_RE.search(prompt)
        task = (task_match.group(1).lower() if task_match else "").strip()
        spec_match = SPEC_RE.search(prompt)
        spec = spec_match.group(1) if spec_match else prompt

        if task == "plan":
            try:
                plan = nl_to_plan_dict(spec)
                return LLMResponse(text=json.dumps(plan), model=self.name)
            except ValueError as exc:
                return LLMResponse(text=json.dumps({"error": str(exc)}), model=self.name)

        # heal / analyze: the caller owns a heuristic path, so abstain cleanly.
        return LLMResponse(text="{}" if json_mode else "", model=self.name)

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        from ..rag.embeddings import HashingEmbedder

        return HashingEmbedder(dim=self.embed_dim).embed(list(texts))
