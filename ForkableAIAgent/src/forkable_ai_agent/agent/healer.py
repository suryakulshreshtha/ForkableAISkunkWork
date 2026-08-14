"""Locator resolution and self-healing.

Resolution walks the candidate ladder from :mod:`browser.locators`. When every
candidate misses - because a developer renamed ``#login-btn`` to
``#signin-btn`` overnight - the healer takes a compact DOM snapshot and scores
each element against the human description.

The scorer is deterministic and runs first; a local LLM is consulted only to
break ties or when the best heuristic score is weak. That ordering keeps the
common case fast and offline-pure, and keeps the model's role to judgement
rather than plumbing.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from ..browser.locators import LocatorCandidate, build_candidates, guess_role, tokens, variants
from ..browser.snapshot import ElementInfo, capture, render
from .memory import Memory, scope_for

INPUT_TAGS = {"input", "textarea", "select"}
CLICK_TAGS = {"button", "a", "summary", "label", "div", "span", "li"}

HEAL_SYSTEM = (
    "You repair broken UI test selectors. You are given a target description and a "
    "numbered list of elements from the live page. Reply with JSON only: "
    '{"index": <number>, "confidence": <0-1>, "reason": "<short>"}. '
    'If nothing matches, use {"index": -1, "confidence": 0, "reason": "no match"}.'
)


class ElementNotFound(RuntimeError):
    """No candidate and no healing strategy could bind the description."""


@dataclass
class Resolution:
    locator: Any
    candidate: LocatorCandidate
    strategy: str
    healed: bool = False
    attempts: int = 0
    confidence: float = 1.0


def _trigrams(text: str) -> set[str]:
    padded = f"  {text} "
    return {padded[i:i + 3] for i in range(len(padded) - 2)}


def token_similarity(a: str, b: str) -> float:
    """Fuzzy 0..1 similarity between two identifier tokens.

    Renames are rarely total: ``password`` becomes ``passphrase``, ``username``
    becomes ``user name``. Exact set overlap misses all of those, so scoring
    falls back through substring, shared prefix and trigram overlap.
    """
    if a == b:
        return 1.0
    if len(a) >= 3 and len(b) >= 3 and (a in b or b in a):
        return 0.75
    prefix = 0
    for x, y in zip(a, b, strict=False):
        if x != y:
            break
        prefix += 1
    if prefix >= 4:
        return 0.6
    grams_a, grams_b = _trigrams(a), _trigrams(b)
    union = grams_a | grams_b
    if not union:
        return 0.0
    jaccard = len(grams_a & grams_b) / len(union)
    return 0.55 * jaccard if jaccard > 0.25 else 0.0


def _match_strength(desc_tokens: Sequence[str], value: str) -> float:
    """Sum of the best per-token similarity against *value*'s tokens."""
    value_tokens = tokens(value)
    if not value_tokens:
        return 0.0
    return sum(max(token_similarity(t, v) for v in value_tokens) for t in desc_tokens)


def score_element(description: str, element: ElementInfo, action: str = "") -> float:
    """Heuristic 0..1 similarity between a description and a live element."""
    desc_tokens = tokens(description)
    if not desc_tokens:
        return 0.0

    fields = (
        (element.testid, 4.0),
        (element.id, 3.2),
        (element.name, 3.2),
        (element.aria, 2.8),
        (element.label, 2.8),
        (element.placeholder, 2.4),
        (element.text, 2.2),
        (element.title, 1.4),
        (element.type, 1.0),
        (element.role, 1.0),
        (element.cls, 0.5),
    )

    best_possible = 4.0 * len(desc_tokens)
    total = 0.0
    spellings = set(variants(description))
    for value, weight in fields:
        if not value:
            continue
        strength = _match_strength(desc_tokens, value)
        if strength:
            total += weight * strength
        # an exact identifier match is the strongest signal available
        if value.strip().lower() in spellings:
            total += weight * len(desc_tokens) * 0.5

    score = total / best_possible if best_possible else 0.0

    # action/shape compatibility
    if action in {"fill", "press", "expect_value"}:
        if element.tag in INPUT_TAGS:
            score += 0.12
        else:
            score -= 0.25
    elif action in {"click", "hover"}:
        if element.tag in CLICK_TAGS or element.role in {"button", "link", "tab"}:
            score += 0.10
        if element.tag == "input" and element.type in {"submit", "button", "checkbox", "radio"}:
            score += 0.10
    elif action in {"check", "uncheck"}:
        score += 0.15 if element.type in {"checkbox", "radio"} else -0.2
    elif action == "select":
        score += 0.15 if element.tag == "select" else -0.15

    if not element.visible:
        score -= 0.3
    return max(0.0, min(1.0, score))


def rank_elements(
    description: str, elements: Sequence[ElementInfo], action: str = ""
) -> list[tuple[ElementInfo, float]]:
    ranked = [(el, score_element(description, el, action)) for el in elements]
    ranked.sort(key=lambda pair: pair[1], reverse=True)
    return ranked


def candidate_from_element(element: ElementInfo, action: str = "", description: str = "") -> LocatorCandidate:
    """Pick the most durable selector that identifies *element*."""
    if element.testid:
        return LocatorCandidate("testid", f'[data-testid="{element.testid}"]', strategy="healed-testid")
    if element.id:
        return LocatorCandidate("css", f"#{element.id}", strategy="healed-id")
    if element.name:
        return LocatorCandidate("css", f'[name="{element.name}"]', strategy="healed-name")
    if element.aria:
        role = element.role or guess_role(description or element.aria, action)
        return LocatorCandidate("role", element.aria, role=role, strategy="healed-aria")
    if element.label:
        return LocatorCandidate("label", element.label, strategy="healed-label")
    if element.placeholder:
        return LocatorCandidate("placeholder", element.placeholder, strategy="healed-placeholder")
    if element.text and element.tag in CLICK_TAGS:
        return LocatorCandidate("text", element.text[:40], strategy="healed-text")
    return LocatorCandidate("css", element.css, strategy="healed-csspath")


def _parse_llm_choice(text: str) -> tuple[int, float, str]:
    if not text:
        return -1, 0.0, ""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return -1, 0.0, ""
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return -1, 0.0, ""
    try:
        index = int(data.get("index", -1))
    except (TypeError, ValueError):
        index = -1
    try:
        confidence = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    return index, confidence, str(data.get("reason", ""))[:200]


class LocatorResolver:
    """Binds natural-language element descriptions to live Playwright locators."""

    def __init__(
        self,
        settings,
        memory: Memory,
        llm: Any = None,
        heuristic_threshold: float = 0.34,
        ask_llm_below: float = 0.62,
    ) -> None:
        self.settings = settings
        self.memory = memory
        self.llm = llm
        self.namespace = getattr(settings, "memory_namespace", "")
        self.heuristic_threshold = heuristic_threshold
        self.ask_llm_below = ask_llm_below
        self.events: list[dict] = []

    # ------------------------------------------------------------------
    def _try_candidate(self, page: Any, candidate: LocatorCandidate) -> Any | None:
        try:
            locator = candidate.build(page)
            count = locator.count()
        except Exception:
            return None
        if count == 0:
            return None
        target = locator.first
        try:
            if not target.is_visible():
                # hidden matches are useless for interaction but fine for presence
                return None
        except Exception:
            return None
        return target

    # ------------------------------------------------------------------
    def resolve(self, page: Any, description: str, action: str = "") -> Resolution:
        scope = scope_for(getattr(page, "url", "") or "", self.namespace)
        known = self.memory.known_keys(description, scope)
        candidates = build_candidates(description, action, known=known)

        attempts = 0
        for candidate in candidates:
            attempts += 1
            locator = self._try_candidate(page, candidate)
            if locator is not None:
                # A cache hit is not a heal: the repair happened on an earlier
                # run, and reporting it as fresh would inflate the healing count
                # on every subsequent run.
                fresh_heal = candidate.strategy.startswith("healed-")
                self.memory.record_success(
                    description, scope, candidate.key, candidate.strategy, healed=fresh_heal,
                )
                return Resolution(
                    locator=locator,
                    candidate=candidate,
                    strategy=candidate.strategy,
                    healed=fresh_heal,
                    attempts=attempts,
                )
            if candidate.strategy == "memory-cache":
                self.memory.record_failure(description, scope, candidate.key)

        return self.heal(page, description, action, attempts=attempts)

    # ------------------------------------------------------------------
    def heal(self, page: Any, description: str, action: str = "", attempts: int = 0) -> Resolution:
        elements = capture(page, limit=140)
        if not elements:
            raise ElementNotFound(
                f"could not locate {description!r}: the page exposed no interactive elements"
            )

        ranked = rank_elements(description, elements, action)
        best, best_score = ranked[0]
        chosen, confidence, reason, source = best, best_score, "heuristic token overlap", "heuristic"

        if self.llm is not None and getattr(self.llm, "name", "") != "rules" and best_score < self.ask_llm_below:
            shortlist = [el for el, _ in ranked[:25]]
            prompt = (
                "# task: heal\n"
                f"Target description: {description}\n"
                f"Intended action: {action or 'interact'}\n\n"
                "Elements:\n"
                f"{render(shortlist, limit=25)}\n"
            )
            try:
                response = self.llm.generate(prompt, system=HEAL_SYSTEM, json_mode=True)
                index, llm_conf, llm_reason = _parse_llm_choice(response.text)
                if 0 <= index < len(shortlist) and llm_conf >= 0.4:
                    chosen = shortlist[index]
                    confidence = max(best_score, llm_conf)
                    reason = llm_reason or "model selection"
                    source = "llm"
            except Exception:
                pass  # a dead model must never break healing

        if confidence < self.heuristic_threshold:
            raise ElementNotFound(
                f"could not locate {description!r}; best candidate "
                f"{chosen.line()[:120]!r} scored {confidence:.2f}"
            )

        candidate = candidate_from_element(chosen, action, description)
        locator = self._try_candidate(page, candidate)
        if locator is None:
            fallback = LocatorCandidate("css", chosen.css, strategy="healed-csspath")
            locator = self._try_candidate(page, fallback)
            if locator is None:
                raise ElementNotFound(
                    f"healing picked an element for {description!r} but no selector bound to it"
                )
            candidate = fallback

        scope = scope_for(getattr(page, "url", "") or "", self.namespace)
        self.memory.record_success(description, scope, candidate.key, candidate.strategy, healed=True)
        self.events.append({
            "description": description,
            "scope": scope,
            "selector": candidate.describe(),
            "confidence": round(confidence, 3),
            "source": source,
            "reason": reason,
        })
        return Resolution(
            locator=locator,
            candidate=candidate,
            strategy=candidate.strategy,
            healed=True,
            attempts=attempts + 1,
            confidence=confidence,
        )
