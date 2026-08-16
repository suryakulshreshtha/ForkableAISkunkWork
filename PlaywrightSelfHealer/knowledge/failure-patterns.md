# Failure patterns and remediation

## selector_not_found

The description did not bind to any element.

- Confirm the page actually rendered the control — take a screenshot before
  blaming the locator. A blank region usually means an upstream step silently
  no-opped.
- Check whether a modal, cookie banner or overlay is intercepting.
- If healing bound it to something new, add a `data-testid` to the app so the
  next run takes the fast path.

## ambiguous_selector

Playwright strict mode resolved the locator to several elements. Scope the
locator to a container, or use the accessible name that distinguishes the two.
Do not reach for `.nth(2)`: index-based selection breaks the moment a row is
inserted.

## timeout

The action waited and gave up.

- The app may genuinely be slow: raise `browser.default_timeout_ms`.
- The element may never appear: the failure is upstream, not here.
- Never paper over this with `sleep`. Web-first assertions retry; sleeps do not,
  and they make the suite slower on a good day and still flaky on a bad one.

## app_unreachable

Nothing was listening. Start the bundled target with `forkable serve`, or point
`--base-url` at a running app. In CI, ensure the server step precedes the test
step and that the port matches.

## offline_guard

Something tried to open a non-loopback socket while the guard was armed. This is
usually a dependency phoning home — telemetry, a font CDN, a source map fetch.
Investigate before disabling the guard; an offline suite that quietly depends on
the internet is not an offline suite.

## dns

A hostname could not be resolved. Air-gapped runs must target `127.0.0.1`. If a
hostname is genuinely required, add a hosts entry pointing at loopback.

## assertion_url

Navigation ended somewhere unexpected. Check the redirect chain and any auth
guard. Assert on a path fragment rather than a fully-qualified URL so the test
survives a port change.

## assertion_text

Expected copy was missing. Either the copy changed or the state never updated.
Where possible assert on a role or test id rather than prose — copy is the most
frequently edited part of any UI.

## visual_regression

Rendered output drifted past tolerance. Open the diff image: red pixels mark the
change. If the change was intended, refresh the baseline. If a font renders
differently between your laptop and CI, pin the container image rather than
raising the tolerance until the check is meaningless.

## browser_missing

Playwright's browser bundle is absent. Install once with network access, or seed
`PLAYWRIGHT_BROWSERS_PATH` from an offline bundle copied from another machine.
