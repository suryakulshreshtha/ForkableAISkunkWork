"""Browser layer: locator ladders, DOM snapshots, Playwright session control."""

from .locators import LocatorCandidate, build_candidates, guess_role, variants
from .session import BrowserSession, BrowserUnavailable, browsers_installed, playwright_installed
from .snapshot import ElementInfo, capture, render

__all__ = [
    "LocatorCandidate",
    "build_candidates",
    "guess_role",
    "variants",
    "BrowserSession",
    "BrowserUnavailable",
    "browsers_installed",
    "playwright_installed",
    "ElementInfo",
    "capture",
    "render",
]
