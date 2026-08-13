"""Hard offline guarantee.

Calling :func:`enforce_offline` patches the stdlib socket layer so that any
attempt to reach an address that is not loopback raises
:class:`OfflineViolation` before a packet leaves the process. DNS resolution
for non-loopback names is blocked too, so nothing leaks to a resolver.

This is deliberately enforced at the socket layer rather than in each client:
it also covers third-party libraries (Playwright's driver, HTTP clients,
telemetry in transitive dependencies) that we do not control.
"""

from __future__ import annotations

import ipaddress
import os
import socket
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from typing import Any

__all__ = [
    "OfflineViolation",
    "enforce_offline",
    "release_offline",
    "is_enforced",
    "allow_hosts",
    "is_loopback_host",
]


class OfflineViolation(OSError):
    """Raised when code tries to open a non-loopback connection in offline mode."""


_DEFAULT_ALLOWED: set[str] = {
    "",
    "localhost",
    "localhost.localdomain",
    "ip6-localhost",
    "ip6-loopback",
}

_extra_allowed: set[str] = set()
_originals: dict[str, Any] = {}
_enforced = False


def is_loopback_host(host: Any) -> bool:
    """True when *host* is a loopback IP or an explicitly allowed local name."""
    if host is None:
        return True
    if isinstance(host, bytes):
        host = host.decode("utf-8", "replace")
    if not isinstance(host, str):
        return False
    name = host.strip().strip("[]").lower()
    if name in _DEFAULT_ALLOWED or name in _extra_allowed:
        return True
    try:
        return ipaddress.ip_address(name).is_loopback
    except ValueError:
        return False


def _check(address: Any, family: int | None = None) -> None:
    if family is not None and getattr(socket, "AF_UNIX", None) == family:
        return
    if isinstance(address, (str, bytes)):
        # AF_UNIX path or similar; not an IP endpoint.
        return
    if isinstance(address, tuple) and address:
        host = address[0]
        if not is_loopback_host(host):
            raise OfflineViolation(
                f"offline mode: refused connection to {host!r}. "
                "ForkableAIAgent only talks to loopback. "
                "Unset FORKABLE_OFFLINE to disable this guard."
            )


@contextmanager
def allow_hosts(hosts: Iterable[str]) -> Iterator[None]:
    """Temporarily treat *hosts* as local (used by tests and mirrors)."""
    added = {h.lower() for h in hosts} - _extra_allowed
    _extra_allowed.update(added)
    try:
        yield
    finally:
        _extra_allowed.difference_update(added)


def enforce_offline() -> None:
    """Install the socket guards. Safe to call more than once."""
    global _enforced
    if _enforced:
        return

    _originals["connect"] = socket.socket.connect
    _originals["connect_ex"] = socket.socket.connect_ex
    _originals["create_connection"] = socket.create_connection
    _originals["getaddrinfo"] = socket.getaddrinfo

    def guarded_connect(self: socket.socket, address: Any) -> Any:
        _check(address, getattr(self, "family", None))
        return _originals["connect"](self, address)

    def guarded_connect_ex(self: socket.socket, address: Any) -> Any:
        _check(address, getattr(self, "family", None))
        return _originals["connect_ex"](self, address)

    def guarded_create_connection(address: Any, *args: Any, **kwargs: Any) -> Any:
        _check(address)
        return _originals["create_connection"](address, *args, **kwargs)

    def guarded_getaddrinfo(host: Any, port: Any, *args: Any, **kwargs: Any) -> Any:
        if not is_loopback_host(host):
            raise OfflineViolation(
                f"offline mode: refused DNS lookup for {host!r}."
            )
        return _originals["getaddrinfo"](host, port, *args, **kwargs)

    socket.socket.connect = guarded_connect  # type: ignore[method-assign]
    socket.socket.connect_ex = guarded_connect_ex  # type: ignore[method-assign]
    socket.create_connection = guarded_create_connection  # type: ignore[assignment]
    socket.getaddrinfo = guarded_getaddrinfo  # type: ignore[assignment]

    # Belt and braces: silence downloaders and telemetry that ship with deps.
    os.environ.setdefault("PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD", "1")
    os.environ.setdefault("PLAYWRIGHT_SKIP_BROWSER_GC", "1")
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    os.environ.setdefault("NO_PROXY", "*")
    os.environ.setdefault("DO_NOT_TRACK", "1")
    _enforced = True


def release_offline() -> None:
    """Restore the original socket functions (used by tests)."""
    global _enforced
    if not _enforced:
        return
    socket.socket.connect = _originals["connect"]  # type: ignore[method-assign]
    socket.socket.connect_ex = _originals["connect_ex"]  # type: ignore[method-assign]
    socket.create_connection = _originals["create_connection"]  # type: ignore[assignment]
    socket.getaddrinfo = _originals["getaddrinfo"]  # type: ignore[assignment]
    _originals.clear()
    _enforced = False


def is_enforced() -> bool:
    return _enforced
