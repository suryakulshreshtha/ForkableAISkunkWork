"""Turning "the log in button" into a Playwright locator.

The agent never hard-codes a selector in a plan. Instead every element step
carries a human description, and this module expands that description into an
ordered ladder of candidate locators, most-stable first:

``data-testid`` -> ARIA role+name -> label -> placeholder -> id/name -> text -> css

A candidate knows three things: how to build a live ``Locator``, how to render
itself as Python source for generated tests, and how to serialise to a cache
key so a healed selector survives across runs.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

RAW_PREFIXES = ("css=", "xpath=", "text=", "id=", "data-testid=", "role=", "//", "#", ".", "[")

_ROLE_HINTS: list[tuple[str, str]] = [
    (r"\bbutton\b|\bsubmit\b|\bcta\b", "button"),
    (r"\blink\b|\banchor\b", "link"),
    (r"\bcheckbox\b|\btick box\b", "checkbox"),
    (r"\bradio\b", "radio"),
    (r"\bdropdown\b|\bselect\b|\bcombobox\b", "combobox"),
    (r"\btab\b", "tab"),
    (r"\bheading\b|\btitle\b|\bheader\b", "heading"),
    (r"\balert\b|\berror\b|\bbanner\b|\bmessage\b|\btoast\b", "alert"),
    (r"\bsearch\b", "searchbox"),
    (r"\bpassword\b|\bfield\b|\binput\b|\btextbox\b|\bemail\b|\busername\b|\btext box\b", "textbox"),
]

# Kept deliberately small: dropping "in" would collapse "log in" to "log" and
# lose the most useful spelling of all - "login".
_STOP = {"the", "a", "an", "please", "element"}

# Attributes commonly used as stable test hooks, in order of preference.
TESTID_ATTRS = ("data-testid", "data-test-id", "data-test", "data-qa", "data-cy")


def normalise(description: str) -> str:
    return re.sub(r"\s+", " ", description.strip().lower())


def tokens(description: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", description.lower()) if t not in _STOP]


#: Nouns people append to name a control ("username field", "log in button").
#: They belong in the description, but never in the accessible name.
UI_NOUNS = {"button", "field", "input", "box", "textbox", "link", "icon", "tab",
            "menu", "checkbox", "dropdown", "label", "text", "control", "form"}


def core(description: str) -> str:
    """"username field" -> "username"; "log in button" -> "log in"."""
    parts = tokens(description)
    while len(parts) > 1 and parts[-1] in UI_NOUNS:
        parts.pop()
    return " ".join(parts) if parts else normalise(description)


def variants(description: str) -> list[str]:
    """Identifier spellings a developer might have used for this element."""
    parts = tokens(core(description))
    if not parts:
        return []
    joined = "".join(parts)
    out = [
        "-".join(parts),
        "_".join(parts),
        joined,
        parts[0] + "".join(p.capitalize() for p in parts[1:]),
    ]
    if len(parts) > 1:
        out.append(parts[-1])
        out.append(parts[0])
    seen: list[str] = []
    for item in out:
        if item and item not in seen:
            seen.append(item)
    return seen


def guess_role(description: str, action: str = "") -> str:
    text = description.lower()
    for pattern, role in _ROLE_HINTS:
        if re.search(pattern, text):
            return role
    if action in {"fill", "press", "expect_value"}:
        return "textbox"
    if action in {"check", "uncheck"}:
        return "checkbox"
    if action == "select":
        return "combobox"
    return "button"


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


@dataclass
class LocatorCandidate:
    kind: str                  # testid | role | label | placeholder | text | css | xpath
    value: str
    role: str = ""
    strategy: str = ""
    exact: bool = False
    meta: dict[str, Any] = field(default_factory=dict)

    # -- runtime -------------------------------------------------------
    def build(self, page: Any) -> Any:
        if self.kind == "testid":
            return page.locator(self.value)
        if self.kind == "role":
            return page.get_by_role(self.role or "button", name=self.value, exact=self.exact)
        if self.kind == "label":
            return page.get_by_label(self.value, exact=self.exact)
        if self.kind == "placeholder":
            return page.get_by_placeholder(self.value, exact=self.exact)
        if self.kind == "text":
            return page.get_by_text(self.value, exact=self.exact)
        if self.kind == "xpath":
            return page.locator(f"xpath={self.value}")
        return page.locator(self.value)

    # -- codegen -------------------------------------------------------
    def code(self, var: str = "page") -> str:
        if self.kind == "role":
            exact = ", exact=True" if self.exact else ""
            return f'{var}.get_by_role("{self.role or "button"}", name="{_escape(self.value)}"{exact})'
        if self.kind in {"label", "placeholder", "text"}:
            method = {"label": "get_by_label", "placeholder": "get_by_placeholder", "text": "get_by_text"}[self.kind]
            exact = ", exact=True" if self.exact else ""
            return f'{var}.{method}("{_escape(self.value)}"{exact})'
        if self.kind == "xpath":
            return f'{var}.locator("xpath={_escape(self.value)}")'
        return f'{var}.locator("{_escape(self.value)}")'

    # -- persistence ---------------------------------------------------
    @property
    def key(self) -> str:
        return f"{self.kind}|{self.role}|{int(self.exact)}|{self.value}"

    @classmethod
    def from_key(cls, key: str, strategy: str = "cache") -> LocatorCandidate:
        kind, role, exact, value = key.split("|", 3)
        return cls(kind=kind, value=value, role=role, exact=bool(int(exact)), strategy=strategy)

    def describe(self) -> str:
        return f"{self.kind}({self.role + ':' if self.role else ''}{self.value})"


def raw_candidate(description: str) -> LocatorCandidate | None:
    """Allow escape hatches: a plan may still carry a literal selector."""
    text = description.strip()
    if text.startswith("xpath=") or text.startswith("//"):
        return LocatorCandidate("xpath", text.removeprefix("xpath="), strategy="literal-xpath")
    if text.startswith("css="):
        return LocatorCandidate("css", text.removeprefix("css="), strategy="literal-css")
    if text.startswith(("#", ".", "[")) and " " not in text:
        return LocatorCandidate("css", text, strategy="literal-css")
    return None


def build_candidates(
    description: str,
    action: str = "",
    known: Sequence[str] = (),
) -> list[LocatorCandidate]:
    """Ordered locator ladder for *description*.

    ``known`` holds cache keys previously proven for this description; they are
    tried first so a healed selector costs nothing on the next run.
    """
    out: list[LocatorCandidate] = []
    for key in known:
        try:
            out.append(LocatorCandidate.from_key(key, strategy="memory-cache"))
        except ValueError:
            continue

    literal = raw_candidate(description)
    if literal:
        out.append(literal)
        return out

    text = core(description)
    full = normalise(description)
    role = guess_role(description, action)
    spellings = variants(description)

    for spelling in spellings[:4]:
        for attr in TESTID_ATTRS[:3]:
            out.append(
                LocatorCandidate("testid", f'[{attr}="{spelling}"]', strategy=f"{attr}")
            )

    out.append(LocatorCandidate("role", text, role=role, strategy="aria-role-name"))
    if full != text:
        out.append(LocatorCandidate("role", full, role=role, strategy="aria-role-name-verbose"))
    out.append(LocatorCandidate("label", text, strategy="label"))
    if role in {"textbox", "searchbox", "combobox"}:
        out.append(LocatorCandidate("placeholder", text, strategy="placeholder"))

    for spelling in spellings[:4]:
        out.append(LocatorCandidate("css", f"#{spelling}", strategy="id"))
        out.append(LocatorCandidate("css", f'[name="{spelling}"]', strategy="name-attr"))
        out.append(LocatorCandidate("css", f'[aria-label*="{spelling}" i]', strategy="aria-label"))

    out.append(LocatorCandidate("text", text, strategy="visible-text"))
    if role in {"textbox", "searchbox"}:
        for spelling in spellings[:3]:
            out.append(
                LocatorCandidate("css", f'input[type="{spelling}"]', strategy="input-type")
            )

    deduped: list[LocatorCandidate] = []
    seen = set()
    for candidate in out:
        if candidate.key not in seen:
            seen.add(candidate.key)
            deduped.append(candidate)
    return deduped
