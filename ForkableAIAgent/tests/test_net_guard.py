"""The offline guarantee is the headline claim, so it gets tested first."""

from __future__ import annotations

import socket

import pytest

from forkable_ai_agent.net_guard import (
    OfflineViolation,
    enforce_offline,
    is_loopback_host,
    release_offline,
)


@pytest.fixture
def armed():
    enforce_offline()
    yield
    release_offline()


def test_loopback_recognition():
    assert is_loopback_host("127.0.0.1")
    assert is_loopback_host("localhost")
    assert is_loopback_host("::1")
    assert not is_loopback_host("example.com")
    assert not is_loopback_host("8.8.8.8")


def test_external_connection_is_refused(armed):
    with pytest.raises(OfflineViolation):
        socket.create_connection(("93.184.216.34", 80), timeout=1)


def test_dns_lookup_is_refused(armed):
    with pytest.raises(OfflineViolation):
        socket.getaddrinfo("example.com", 443)


def test_loopback_still_works(armed, demo_app):
    with socket.create_connection(("127.0.0.1", demo_app.port), timeout=2) as sock:
        assert sock is not None


def test_guard_releases_cleanly():
    enforce_offline()
    release_offline()
    # after release the patched functions are gone; resolving localhost is fine
    assert socket.getaddrinfo("127.0.0.1", 80)
