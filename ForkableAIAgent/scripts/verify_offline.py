#!/usr/bin/env python3
"""Prove the agent never leaves the machine.

Arms the socket guard, then attempts a set of outbound connections that a
misbehaving dependency might make. Every one must be refused. Finally it runs a
complete plan against the bundled demo target to show that real work still
happens with the guard armed.

    python scripts/verify_offline.py
"""

from __future__ import annotations

import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from forkable_ai_agent.agent import ForkableAgent  # noqa: E402
from forkable_ai_agent.config import load_settings  # noqa: E402
from forkable_ai_agent.net_guard import OfflineViolation, enforce_offline  # noqa: E402

PROBES = [
    ("tcp to a public IP", lambda: socket.create_connection(("1.1.1.1", 443), timeout=2)),
    ("dns lookup", lambda: socket.getaddrinfo("cdn.playwright.dev", 443)),
    ("tcp to a hostname", lambda: socket.create_connection(("registry.npmjs.org", 443), timeout=2)),
    ("telemetry-style beacon", lambda: socket.create_connection(("collector.example.com", 80), timeout=2)),
]


def main() -> int:
    enforce_offline()
    failures = 0

    print("outbound probes (all must be refused)")
    for name, probe in PROBES:
        try:
            probe()
            print(f"  LEAK  {name} succeeded - the guard is not holding")
            failures += 1
        except OfflineViolation:
            print(f"  ok    {name} refused")
        except OSError as exc:
            print(f"  ok    {name} failed at the OS level ({type(exc).__name__})")

    print("\nloopback must still work")
    settings = load_settings()
    settings.app.port = 8791
    agent = ForkableAgent(settings, probe_llm=False)
    started = agent.ensure_app()
    try:
        with socket.create_connection((settings.app.host, settings.app.port), timeout=2):
            print("  ok    demo target reachable on loopback")
    except OSError as exc:
        print(f"  FAIL  loopback blocked: {exc}")
        failures += 1

    print("\nreal work with the guard armed")
    try:
        plan = agent.plan("go to the login page\nfill username with demo\nclick log in")
        print(f"  ok    planned {len(plan.steps)} steps via the {plan.source} engine")
    except Exception as exc:
        print(f"  FAIL  planning: {exc}")
        failures += 1
    finally:
        if started:
            agent.stop_app()

    print("\nRESULT:", "PASS - nothing escaped" if not failures else f"FAIL - {failures} problem(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
