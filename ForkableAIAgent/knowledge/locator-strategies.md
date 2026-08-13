# Locator strategies

## Preference order

The agent tries locators in a fixed order, most durable first. Each rung
survives a different kind of change, so the ladder degrades gracefully instead
of failing outright.

1. **Test id** — `[data-testid="..."]`, `data-test`, `data-qa`, `data-cy`.
   Survives copy changes, restyling and DOM restructuring. Only breaks when a
   developer deletes the hook deliberately.
2. **ARIA role + accessible name** — `get_by_role("button", name="log in")`.
   Survives id churn and class renames. Breaks when the visible label is
   reworded. This is the rung to prefer when no test id exists, because it
   asserts the same thing a screen reader would see.
3. **Label** — `get_by_label("Password")`. Ties an input to its `<label for>`.
4. **Placeholder** — weaker than a label; placeholders are often marketing copy.
5. **Id / name attribute** — `#username`, `[name="username"]`. Fast, but the
   first thing a refactor churns, especially under CSS-in-JS or hashed builds.
6. **Visible text** — `get_by_text("Sign out")`. Fine for links, fragile for
   anything localised.
7. **CSS path** — `form > div:nth-of-type(2) > input`. Last resort. Records the
   shape of the DOM, so any structural change invalidates it.

## Rules of thumb

- Never assert on a class name. Classes are styling, not identity, and utility
  frameworks rewrite them wholesale.
- Prefer one strong locator over a chain of weak ones. `div > div > span > a` is
  four chances to break.
- Scope before you disambiguate: `page.get_by_role("row", name="nightly-ingest")
  .get_by_role("button", name="retry")` beats an `nth=3` index.
- If a description resolves to several elements, the fix is a narrower
  description or a scoped container, not a strict-mode suppression.
- When healing repairs a locator, treat that as a bug report against the app:
  the durable fix is adding a `data-testid`, not letting the agent guess forever.

## Why descriptions, not selectors, live in plans

A plan step carries `target: "password field"`, never `#pwd`. Binding happens at
run time against the live DOM. That indirection is what makes healing possible:
there is no hard-coded selector to break, only a description to re-bind.
