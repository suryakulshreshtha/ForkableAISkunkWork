"""Playwright lifecycle management.

Playwright is imported lazily so the rest of the agent - planning, RAG,
codegen, reporting - stays importable and testable on a machine where browsers
were never installed. That matters for air-gapped setups where the browser
bundle arrives separately.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


class BrowserUnavailable(RuntimeError):
    """Playwright or its browser binaries are missing."""


def playwright_installed() -> bool:
    try:
        import playwright  # noqa: F401
    except ImportError:
        return False
    return True


def browsers_path() -> Path:
    custom = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if custom and custom not in {"0"}:
        return Path(custom)
    home = Path.home()
    if os.name == "nt":  # pragma: no cover
        return home / "AppData" / "Local" / "ms-playwright"
    if os.uname().sysname == "Darwin":  # pragma: no cover
        return home / "Library" / "Caches" / "ms-playwright"
    return home / ".cache" / "ms-playwright"


def browsers_installed(engine: str = "chromium") -> bool:
    root = browsers_path()
    if not root.exists():
        return False
    return any(p.name.startswith(engine) for p in root.iterdir())


class BrowserSession:
    """Context manager owning a Playwright instance, browser, context and page."""

    def __init__(self, settings, engine: str | None = None, headless: bool | None = None) -> None:
        self.settings = settings
        self.engine = engine or settings.browser.engine
        self.headless = settings.browser.headless if headless is None else headless
        self._pw: Any = None
        self._browser: Any = None
        self._context: Any = None
        self.page: Any = None
        self.artifacts_dir = settings.path(settings.browser.artifacts_dir)

    # ------------------------------------------------------------------
    def start(self) -> BrowserSession:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover - depends on install
            raise BrowserUnavailable(
                "playwright is not installed. Run: pip install playwright"
            ) from exc

        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self._pw = sync_playwright().start()
        launcher = getattr(self._pw, self.engine, None)
        if launcher is None:
            raise BrowserUnavailable(f"unknown browser engine {self.engine!r}")
        try:
            self._browser = launcher.launch(
                headless=self.headless,
                slow_mo=self.settings.browser.slow_mo_ms or 0,
                args=["--no-sandbox", "--disable-dev-shm-usage"] if self.engine == "chromium" else None,
            )
        except Exception as exc:
            self.stop()
            raise BrowserUnavailable(
                f"could not launch {self.engine}: {exc}. "
                "Install browsers once with 'python -m playwright install chromium', "
                "or point PLAYWRIGHT_BROWSERS_PATH at a pre-seeded bundle."
            ) from exc

        self._context = self._browser.new_context(
            viewport={
                "width": self.settings.browser.viewport_width,
                "height": self.settings.browser.viewport_height,
            },
            ignore_https_errors=True,
        )
        self._context.set_default_timeout(self.settings.browser.default_timeout_ms)
        if self.settings.browser.trace:
            self._context.tracing.start(screenshots=True, snapshots=True, sources=False)
        self.page = self._context.new_page()
        return self

    # ------------------------------------------------------------------
    def screenshot(self, name: str, full_page: bool = False) -> str:
        if self.page is None:
            return ""
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in name) or "shot"
        path = self.artifacts_dir / f"{safe}.png"
        try:
            self.page.screenshot(path=str(path), full_page=full_page)
        except Exception:
            return ""
        return str(path)

    def stop(self) -> None:
        try:
            if self._context is not None and self.settings.browser.trace:
                self._context.tracing.stop(path=str(self.artifacts_dir / "trace.zip"))
        except Exception:
            pass
        for closer in (self._context, self._browser):
            try:
                if closer is not None:
                    closer.close()
            except Exception:
                pass
        try:
            if self._pw is not None:
                self._pw.stop()
        except Exception:
            pass
        self._pw = self._browser = self._context = self.page = None

    def __enter__(self) -> BrowserSession:
        return self.start()

    def __exit__(self, *exc_info: Any) -> None:
        self.stop()
