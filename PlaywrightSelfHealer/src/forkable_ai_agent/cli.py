"""Command line interface.

``argparse`` rather than Typer or Click: the core of this tool must install and
run on a locked-down box from a single wheelhouse, and every dependency removed
from the critical path is one less thing to mirror.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from . import __version__
from .config import load_settings
from .net_guard import enforce_offline

GREEN, RED, YELLOW, DIM, BOLD, RESET = (
    "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[1m", "\033[0m"
)


def _colour(text: str, code: str) -> str:
    if os.environ.get("NO_COLOR") or not sys.stdout.isatty():
        return text
    return f"{code}{text}{RESET}"


def _read_spec(spec: str | None, file: str | None) -> str:
    if file:
        return Path(file).read_text(encoding="utf-8")
    if spec:
        return spec
    if not sys.stdin.isatty():
        return sys.stdin.read()
    raise SystemExit("provide a spec argument, --file, or pipe one on stdin")


def _agent(args: argparse.Namespace):
    from .agent import ForkableAgent

    settings = load_settings(getattr(args, "config", None))
    if getattr(args, "allow_network", False):
        settings.offline = False
    if getattr(args, "base_url", ""):
        pass  # handled per-command
    if getattr(args, "headed", False):
        settings.browser.headless = False
    if getattr(args, "browser", ""):
        settings.browser.engine = args.browser
    if getattr(args, "variant", ""):
        # v1 and v2 are different DOMs at the same path; keep their memories apart.
        settings.memory_namespace = args.variant
    if settings.offline:
        enforce_offline()
    return ForkableAgent(settings)


# ----------------------------------------------------------------------
def cmd_doctor(args: argparse.Namespace) -> int:
    agent = _agent(args)
    print(_colour(f"PlaywrightSelfHealer {__version__} - offline readiness", BOLD))
    failures = 0
    for check in agent.doctor():
        if check.ok:
            mark = _colour("PASS", GREEN)
        elif check.required:
            mark = _colour("FAIL", RED)
            failures += 1
        else:
            mark = _colour("WARN", YELLOW)
        print(f"  [{mark}] {check.name:<20} {_colour(check.detail, DIM)}")
    print()
    print("Offline mode:", "armed" if agent.settings.offline else _colour("disabled", YELLOW))
    return 1 if failures else 0


def cmd_serve(args: argparse.Namespace) -> int:
    from .testapp import DemoApp

    settings = load_settings(args.config)
    if args.variant:
        os.environ["FORKABLE_UI_VARIANT"] = args.variant
    app = DemoApp(host=settings.app.host, port=args.port or settings.app.port)
    print(f"demo target on {app.base_url}  (accounts: demo/secret123)  ctrl-c to stop")
    app.serve_forever()
    return 0


def cmd_index(args: argparse.Namespace) -> int:
    agent = _agent(args)
    manifest = agent.index()
    print(
        f"indexed {manifest['count']} chunks from {manifest['files']} files "
        f"using the {manifest['embedder']} embedder (dim {manifest['dim']})"
    )
    return 0


def cmd_ask(args: argparse.Namespace) -> int:
    agent = _agent(args)
    answer, hits = agent.ask(args.question)
    print(answer)
    if hits:
        print(_colour("\nsources:", DIM))
        for i, hit in enumerate(hits, 1):
            print(_colour(f"  [{i}] {hit.citation}  score={hit.score:.3f}", DIM))
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    agent = _agent(args)
    plan = agent.plan(_read_spec(args.spec, args.file), args.base_url)
    if args.json:
        print(plan.to_json())
    else:
        print(_colour(f"{plan.name}  ({plan.source})", BOLD))
        for i, step in enumerate(plan.steps, 1):
            bits = [f"{i:>2}. {step.action}"]
            if step.target:
                bits.append(f"target={step.target!r}")
            if step.value:
                bits.append(f"value={step.value!r}")
            print("    " + "  ".join(bits))
    if args.out:
        Path(args.out).write_text(plan.to_json(), encoding="utf-8")
        print(_colour(f"\nwrote {args.out}", DIM))
    return 0


def cmd_generate(args: argparse.Namespace) -> int:
    agent = _agent(args)
    plan = agent.plan(_read_spec(args.spec, args.file), args.base_url)
    generated = agent.generate(plan, out_dir=args.out)
    print(f"wrote {generated.path}")
    if generated.locators:
        print(_colour("locator strategies used:", DIM))
        for note in generated.locators:
            print(_colour(f"  - {note}", DIM))
    if args.show:
        print()
        print(generated.code)
    return 0


def _print_result(result, agent, report: bool) -> None:
    status = result.status
    colour = GREEN if status == "passed" else RED
    print(_colour(f"\n{status.upper()}", colour), f"{result.plan.name}  ({result.duration_s:.1f}s)")
    for step in result.steps:
        mark = {"passed": _colour("ok  ", GREEN), "failed": _colour("fail", RED),
                "warned": _colour("warn", YELLOW), "skipped": _colour("skip", DIM)}[step.status]
        healed = _colour(" [healed]", YELLOW) if step.healed else ""
        detail = f"  {step.selector}" if step.selector else ""
        print(f"  {mark} {step.index:>2}. {step.step.action:<14}"
              f"{step.step.target or step.step.value or '':<28}"
              f"{_colour(detail, DIM)}{healed}")
        if step.message:
            print(_colour(f"       {step.message}", DIM))
    if result.diagnosis:
        d = result.diagnosis
        print(_colour(f"\ndiagnosis [{d.category}] confidence {d.confidence:.2f} via {d.source}", BOLD))
        print(f"  cause: {d.likely_cause}")
        print(f"  fix:   {d.suggested_fix}")
        if d.citations:
            print(_colour(f"  from:  {', '.join(d.citations)}", DIM))
    if report:
        print(_colour(f"\nreport: {agent.report(result)}", DIM))


def cmd_run(args: argparse.Namespace) -> int:
    if args.variant:
        os.environ["FORKABLE_UI_VARIANT"] = args.variant
    agent = _agent(args)
    spec = _read_spec(args.spec, args.file)
    plan = agent.planner.load_plan(args.file) if (args.file or "").endswith(".json") else agent.plan(spec, args.base_url)
    result = agent.run(plan, base_url=args.base_url, headed=args.headed)
    _print_result(result, agent, report=not args.no_report)
    return 0 if result.status == "passed" else 1


def cmd_heal_report(args: argparse.Namespace) -> int:
    agent = _agent(args)
    rows = agent.memory.healing_report()
    if not rows:
        print("no locators learned yet - run a test first")
        return 0
    if args.json:
        print(json.dumps(rows, indent=2))
        return 0
    print(f"{'scope':<14}{'description':<26}{'locator':<46}{'hits':>6}{'conf':>7}  healed")
    for row in rows:
        print(f"{row['scope']:<14}{row['description'][:25]:<26}{row['locator'][:45]:<46}"
              f"{row['hits']:>6}{row['confidence']:>7.2f}  {'yes' if row['healed'] else ''}")
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    """Run the same spec against the stable UI, then against the refactored one."""
    spec = (
        "Test: login_happy_path\n"
        "go to the login page\n"
        "fill username with demo\n"
        "fill password with secret123\n"
        "click log in\n"
        "should be redirected to /dashboard\n"
        "should see Welcome\n"
    )
    exit_code = 0
    for variant, label in (("v1", "stable UI"), ("v2", "refactored UI - ids and labels changed")):
        os.environ["FORKABLE_UI_VARIANT"] = variant
        os.environ["FORKABLE_MEMORY_NS"] = variant
        print(_colour(f"\n=== {variant}: {label} ===", BOLD))
        agent = _agent(args)
        result = agent.run(spec, headed=args.headed)
        _print_result(result, agent, report=not args.no_report)
        if result.status != "passed":
            exit_code = 1
    os.environ.pop("FORKABLE_UI_VARIANT", None)
    os.environ.pop("FORKABLE_MEMORY_NS", None)
    return exit_code


# ----------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="forkable",
        description="Offline Playwright AI agent: plan, generate, run, heal and explain UI tests.",
    )
    parser.add_argument("--version", action="version", version=f"PlaywrightSelfHealer {__version__}")
    parser.add_argument("--config", help="path to agent.toml")
    parser.add_argument("--allow-network", action="store_true",
                        help="disarm the loopback-only socket guard")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("doctor", help="check offline readiness")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("serve", help="serve the bundled demo target")
    p.add_argument("--port", type=int, default=0)
    p.add_argument("--variant", choices=["v1", "v2"], default="")
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("index", help="build the local RAG index")
    p.set_defaults(func=cmd_index)

    p = sub.add_parser("ask", help="ask the local knowledge base")
    p.add_argument("question")
    p.set_defaults(func=cmd_ask)

    p = sub.add_parser("plan", help="turn a natural-language spec into a test plan")
    p.add_argument("spec", nargs="?")
    p.add_argument("--file")
    p.add_argument("--base-url", default="")
    p.add_argument("--json", action="store_true")
    p.add_argument("--out")
    p.set_defaults(func=cmd_plan)

    p = sub.add_parser("generate", help="emit a pytest + Playwright file from a spec")
    p.add_argument("spec", nargs="?")
    p.add_argument("--file")
    p.add_argument("--base-url", default="")
    p.add_argument("--out", default="tests/generated")
    p.add_argument("--show", action="store_true")
    p.set_defaults(func=cmd_generate)

    p = sub.add_parser("run", help="execute a spec or plan with self-healing")
    p.add_argument("spec", nargs="?")
    p.add_argument("--file")
    p.add_argument("--base-url", default="")
    p.add_argument("--browser", choices=["chromium", "firefox", "webkit"], default="")
    p.add_argument("--headed", action="store_true")
    p.add_argument("--variant", choices=["v1", "v2"], default="",
                   help="force the demo app UI variant (v2 exercises healing)")
    p.add_argument("--no-report", action="store_true")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("heal-report", help="show learned and healed locators")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_heal_report)

    p = sub.add_parser("demo", help="run the login flow on both UI variants")
    p.add_argument("--headed", action="store_true")
    p.add_argument("--browser", default="")
    p.add_argument("--no-report", action="store_true")
    p.set_defaults(func=cmd_demo)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(_colour(f"error: {type(exc).__name__}: {exc}", RED), file=sys.stderr)
        if os.environ.get("FORKABLE_TRACEBACK"):
            raise
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
