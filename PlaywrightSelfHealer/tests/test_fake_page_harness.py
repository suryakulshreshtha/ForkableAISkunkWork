"""The harness itself needs testing before anything can be tested with it."""

from __future__ import annotations

from tests.support.fake_page import FakePage


def test_parses_login_form(demo_app, variant_v1):
    page = FakePage(demo_app.base_url)
    page.goto("/login")
    assert "Sign in" in page.inner_text("body")
    assert page.locator('[data-testid="username"]').count() == 1
    assert page.get_by_role("button", name="log in").count() == 1
    assert page.get_by_label("username").count() == 1


def test_login_round_trip(demo_app, variant_v1):
    page = FakePage(demo_app.base_url)
    page.goto("/login")
    page.locator("#username").first.fill("demo")
    page.locator("#password").first.fill("secret123")
    page.get_by_role("button", name="log in").first.click()
    assert "/dashboard" in page.url
    assert "Welcome, demo" in page.inner_text("body")


def test_bad_credentials_show_error(demo_app, variant_v1):
    page = FakePage(demo_app.base_url)
    page.goto("/login")
    page.locator("#username").first.fill("demo")
    page.locator("#password").first.fill("wrong")
    page.get_by_role("button", name="log in").first.click()
    assert "Invalid username or password" in page.inner_text("body")


def test_v2_breaks_the_naive_selectors(demo_app, variant_v2):
    page = FakePage(demo_app.base_url)
    page.goto("/login")
    assert page.locator('[data-testid="username"]').count() == 0
    assert page.locator("#username").count() == 0
    assert page.get_by_label("username").count() == 0
    # ...but a human can still see the field
    assert page.get_by_label("User name").count() == 1


def test_snapshot_shape_matches_injected_js(demo_app, variant_v1):
    page = FakePage(demo_app.base_url)
    page.goto("/login")
    elements = page.evaluate("snapshot", 120)
    keys = {"tag", "id", "name", "type", "testid", "aria", "role",
            "placeholder", "title", "cls", "label", "text", "visible", "css"}
    assert elements and keys <= set(elements[0])
