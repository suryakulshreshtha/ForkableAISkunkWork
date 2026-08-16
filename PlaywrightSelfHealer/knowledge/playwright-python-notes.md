# Playwright for Python — working notes

## Sync vs async

This agent uses the sync API. It is easier to reason about inside pytest, and
the automation is I/O-bound on the browser rather than on concurrency. The async
API matters when driving many contexts at once; a test agent driving one page
does not benefit.

## Auto-waiting

Playwright actionability checks wait for an element to be attached, visible,
stable, enabled and unobscured before acting. This removes most explicit waits.
The correct response to flakiness is almost never a sleep — it is a web-first
assertion (`expect(...).to_be_visible()`) which retries until timeout.

## Locators are lazy

A `Locator` is a query description, not a resolved handle. It re-queries on each
use, which is why locators survive re-renders where `ElementHandle` does not.
Prefer locators everywhere.

## Useful pieces

- `page.get_by_role(role, name=...)` — name matching is case-insensitive and
  substring-based unless `exact=True`.
- `page.get_by_label`, `get_by_placeholder`, `get_by_text`, `get_by_test_id`.
- `expect(page).to_have_url(re.compile(...))` for redirect assertions.
- `context.tracing.start(screenshots=True, snapshots=True)` produces a trace
  viewable offline with `playwright show-trace trace.zip`.
- `page.screenshot(path=..., full_page=True)` for visual baselines.

## Cross-browser

Chromium, Firefox and WebKit are all driven by the same API. Differences that
bite in practice: font rendering (breaks naive visual diffs), file-input
handling, and WebKit's stricter cookie policies.

## Offline considerations

Browsers are downloaded once from a CDN. On an air-gapped machine, copy the
`ms-playwright` cache directory from a connected machine and point
`PLAYWRIGHT_BROWSERS_PATH` at it. Version-match the Python package to the bundle
or the driver will refuse to start.
