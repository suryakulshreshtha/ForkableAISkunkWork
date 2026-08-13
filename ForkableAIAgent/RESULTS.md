# Verification results

Everything below was executed, not asserted. Environment: Python 3.12.3,
Playwright 1.62, Chromium 141.0.7390.37, no Ollama daemon present (which is
itself a useful test — the whole suite passes with no model at all).

```
96 passed in 10.7s          # full suite, includes 3 real-browser tests
ruff check src tests scripts # All checks passed!
scripts/verify_offline.py   # PASS - nothing escaped
```

## Requested capabilities

| # | Capability (from the brief) | Status | Evidence |
|---|---|---|---|
| 1 | Natural language → automated tests | **PASS** | `forkable plan/run --file examples/nl_specs/login.txt`; `tests/test_planner.py` (15 tests) |
| 2 | Self-healing locators | **PASS** | v2 run heals `username` → `#usr_1a2b` in real Chromium; `tests/test_healer.py` (17 tests) |
| 3 | AI-assisted test generation | **PASS** | `forkable generate` output executed standalone in Chromium and passed |
| 4 | Automatic failure analysis | **PASS** | 7-way classification + RAG citations; `tests/test_analyzer_and_report.py` |
| 5 | Visual UI validation | **PASS** | Pillow diff, tolerance, baselines, red-overlay heatmaps; `tests/test_visual.py` |
| 6 | Cross-browser testing | **PARTIAL** | Chromium verified end-to-end. Firefox/WebKit are wired (`--browser`) but their bundles were not downloadable in this sandbox, so untested here |
| 7 | API + UI test automation | **PARTIAL** | UI fully covered; the demo target exposes `/health` and assertions poll live state, but there is no dedicated `api_call` action yet |
| 8 | Regression testing | **PASS** | Same spec passes across a breaking UI refactor; locator memory persists across runs |
| 9 | CI/CD integration | **PARTIAL** | `.github/workflows/ci.yml` written with a 3.11/3.12 matrix, browser cache and artifact upload — **not executed**, since I cannot push to Actions |
| 10 | Context-aware execution | **PASS** | Memory scoped per URL path; RAG grounds diagnoses in local notes |
| 11 | RAG + LLM integration | **PASS** (offline path) / **PARTIAL** (model path) | Hybrid BM25+dense retrieval verified. The Ollama client is complete and unit-tested against fakes, but **no daemon existed here**, so live inference is unverified |
| 12 | Runs fully offline, no internet | **PASS** | Socket + DNS guard; 4/4 egress probes refused; suite green with `FORKABLE_LLM_PROVIDER=none` |
| 13 | Repo named `ForkableAISkunkWork` | **PASS** | Local git repo, 6 commits, `main` branch |
| 14 | Project in folder `ForkableAIAgent` | **PASS** | `ForkableAISkunkWork/ForkableAIAgent/` |
| 15 | Pushed to GitHub | **FAIL** | No credentials in this environment. `scripts/push_to_github.sh` publishes it in one command |

## Component-level check

| Component | Tests | Status | Note |
|---|---|---|---|
| `net_guard` | 5 | **PASS** | External TCP and DNS both refused; loopback unaffected |
| `config` | — | **PASS** | TOML + env precedence; exercised by every fixture |
| `schema` | 3 | **PASS** | Invalid actions and empty plans rejected |
| `llm/rules` (deterministic planner) | 15 | **PASS** | 8 phrasing families; credential shorthand expansion |
| `llm/ollama_client` | — | **UNVERIFIED** | No daemon available. Model resolution against `ollama list` is implemented but untested live |
| `rag/*` | 6 | **PASS** | Determinism, topic separation, BM25 ranking, persistence |
| `browser/locators` | 3 | **PASS** | Ladder ordering; `core()` noun stripping |
| `browser/snapshot` | 1 | **PASS** | Harness reproduces the injected-JS shape exactly |
| `browser/session` | — | **PASS** | Used by all 3 e2e tests |
| `agent/healer` | 17 | **PASS** | Fuzzy similarity, ranking, healing, cache reuse, stale demotion |
| `agent/executor` | 7 | **PASS** | Both variants, negative paths, optional steps, diagnosis |
| `agent/generator` | 12 | **PASS** | 5 code-injection attempts rejected |
| `agent/memory` | 5 | **PASS** | Scoring, persistence, reporting |
| `agent/analyzer` | 8 | **PASS** | 7 categories + unknown fallback |
| `visual/diff` | 4 | **PASS** | Tolerance, ratio threshold, size change, diff output |
| `reporting` | 3 | **PASS** | Self-contained, HTML-escaped |
| `testapp` | 5 | **PASS** | Both variants, auth, session, error states |
| `cli` | 8 | **PASS** | All 9 commands parse; plan/generate/doctor exercised |

## Live evidence

Same spec, same command, across a UI refactor that deleted every `data-testid`
and renamed every id:

```
=== v1: stable UI ===
PASSED login_happy_path  (0.3s)
  ok  2. fill   username   testid([data-testid="username"])
  ok  4. click  log in     testid([data-testid="login"])

=== v2: refactored UI - ids and labels changed ===
PASSED login_happy_path  (0.4s)
  ok  2. fill   username   css(#usr_1a2b) [healed]
  ok  3. fill   password   css(input[type="password"])
  ok  4. click  log in     role(button:log in)
```

Note that only one step actually healed. Password fell through to the
`input[type=password]` rung and the button bound by ARIA role — healing stayed
the last resort, which is the intended behaviour.

Generated code, executed standalone:

```
$ forkable generate --file examples/nl_specs/login.txt
$ pytest tests/generated/test_login_happy_path.py --browser chromium
1 passed in 1.02s
```

## Known gaps

1. **Not on GitHub.** No credentials here. One command fixes it.
2. **Ollama path unverified live.** No daemon in this sandbox. The client,
   model resolution and prompt contracts are written and unit-tested against
   fakes; expect to shake out real bugs on first contact with a live model.
3. **Firefox/WebKit untested.** Wired but their bundles could not be fetched.
4. **No dedicated API-testing action.** Assertions are UI-only; an
   `api_call` step type is the obvious next addition.
5. **CI never ran.** The workflow is written against a matrix I could not execute.
6. **Memory is scoped per URL path**, so the demo's two variants at `/login`
   share entries. Real apps do not serve two DOMs at one path; if yours does,
   scope the memory file per environment.
7. **Rule grammar is English-only** and covers roughly 20 phrasing families. It
   is a floor, not a replacement for a model.
