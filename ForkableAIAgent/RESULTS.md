# Verification results

Everything below was executed, not asserted. Environment: Python 3.12.3,
Playwright 1.62, Chromium 141.0.7390.37.

```
125 passed in 17.4s          # full suite, includes 5 real-browser tests
ruff check src tests scripts # All checks passed!
scripts/verify_offline.py    # PASS - nothing escaped
scripts/ci_local.sh          # CI would pass  (7/7 stages)
```

## Requested capabilities

| # | Capability (from the brief) | Status | Evidence |
|---|---|---|---|
| 1 | Natural language to automated tests | **PASS** | `tests/test_planner.py` (15); 20+ phrasing families |
| 2 | Self-healing locators | **PASS** | v2 run heals `username` to `#usr_1a2b` in real Chromium; `tests/test_healer.py` (17) |
| 3 | AI-assisted test generation | **PASS** | Generated file executed standalone in Chromium and passed |
| 4 | Automatic failure analysis | **PASS** | 10-way classification + RAG citations + LLM narration |
| 5 | Visual UI validation | **PASS** | Tolerance, ratio threshold, size change, diff heatmaps |
| 6 | Cross-browser testing | **PARTIAL** | Chromium verified end-to-end. Firefox/WebKit are wired via `--browser`; only the Chromium bundle exists in this sandbox, so they remain untested |
| 7 | API + UI test automation | **PASS** | `api_request` / `expect_status` / `expect_json` through `page.request`; UI login authenticates the API call in real Chromium (`tests/test_api_steps.py`, 8) |
| 8 | Regression testing | **PASS** | Same spec passes across a breaking refactor; namespaced locator memory persists |
| 9 | CI/CD integration | **PARTIAL** | Workflow written; `scripts/ci_local.sh` runs all 7 stages locally and passes. GitHub Actions itself still unrun |
| 10 | Context-aware execution | **PASS** | Memory namespaced per environment + URL path; RAG grounds diagnoses |
| 11 | RAG + LLM integration | **PASS** | Hybrid BM25+dense verified; full Ollama path verified over real HTTP (`tests/test_llm_path.py`, 17) |
| 12 | Runs fully offline | **PASS** | Socket + DNS guard; 4/4 egress probes refused; suite green with `FORKABLE_LLM_PROVIDER=none` |
| 13 | Repo named `ForkableAISkunkWork` | **PASS** | Local git repo, 8 commits on `main` |
| 14 | Project in folder `ForkableAIAgent` | **PASS** | `ForkableAISkunkWork/ForkableAIAgent/` |
| 15 | Pushed to GitHub | **FAIL** | No credentials here. `scripts/push_to_github.sh` publishes in one command |

## What changed since the first pass

| Gap | Resolution |
|---|---|
| Ollama path never exercised | `tests/support/fake_ollama.py` serves the real endpoints on loopback. 17 tests now cover model resolution, payload shape, JSON mode, batch + single embeddings, planner retry/fallback, healing tie-break, grounded answering, failure narration, and a 500 from the daemon |
| No API testing | Three new step types, a JSON API on the demo target (`/api/jobs`, `/api/login`), grammar, codegen, harness support, 8 unit + 2 e2e tests |
| v1/v2 memory collision | `memory_namespace` setting (`FORKABLE_MEMORY_NS`, or automatic via `--variant`). Every entry now sits at confidence 1.00 in its own namespace |
| CI unverifiable | `scripts/ci_local.sh` mirrors the workflow. It immediately caught a real bug: CI sets `FORKABLE_LLM_PROVIDER=none`, which forced the rule engine and broke every LLM-path test - that would have failed on the first Actions run |
| No reproducible environment | `Dockerfile` on the pinned Playwright image + `docker-compose.yml` with an optional Ollama profile. Pins fonts, so visual baselines are portable |
| `baselines/` empty and untracked | `baselines/README.md` explaining creation, review and the font caveat |

## Component-level check

| Component | Tests | Status |
|---|---|---|
| `net_guard` | 5 | **PASS** |
| `llm/rules` (deterministic planner) | 15 | **PASS** |
| `llm/ollama_client` + wiring | 17 | **PASS** - over real HTTP against a scripted daemon |
| `rag/*` | 6 | **PASS** |
| `browser/locators` + `snapshot` | 4 | **PASS** |
| `agent/healer` | 17 | **PASS** |
| `agent/executor` (UI) | 7 | **PASS** |
| `agent/executor` (API) | 8 | **PASS** |
| `agent/generator` | 12 | **PASS** - 5 code-injection attempts rejected |
| `agent/memory` | 7 | **PASS** |
| `agent/analyzer` + reporting | 10 | **PASS** |
| `visual/diff` | 4 | **PASS** |
| `testapp` | 5 | **PASS** |
| `cli` + facade | 8 | **PASS** |
| DOM harness (self-test) | 5 | **PASS** |
| Real browser (e2e) | 5 | **PASS** |

## Live evidence

Same spec, same command, across a refactor that deleted every `data-testid` and
renamed every id:

```
=== v1: stable UI ===              === v2: refactored UI ===
ok 2. fill  username               ok 2. fill  username  css(#usr_1a2b) [healed]
      testid([data-testid=...])    ok 3. fill  password  css(input[type="password"])
ok 4. click log in                 ok 4. click log in    role(button:log in)
PASSED (0.2s)                      PASSED (0.3s)
```

Only one step healed. Password fell through to the `input[type=password]` rung
and the button bound by ARIA role - healing stayed the last resort.

Learned locators, now correctly separated:

```
v1:/login  username  testid||0|[data-testid="username"]   1  1.00
v2:/login  username  css||0|#usr_1a2b                     1  1.00  healed
```

## Bugs the verification caught

1. **Nested f-string** in the generator was a syntax error on Python 3.11 - a
   version in the CI matrix. The module would not have imported.
2. **Cache hits reported as heals**, inflating the healing count on every rerun.
   `memory-cache` and `healed-*` are now distinct.
3. **Greedy credential regex** swallowed `"demo and password secret123"` as one value.
4. **`FORKABLE_LLM_PROVIDER=none` in CI** silently disabled the LLM-path tests.
5. **API action sets collided** - the new steps were appended to `ELEMENT_ACTIONS`
   as well as `ACTIONS`, so `expect_status` demanded a DOM target. A disjointness
   assertion now guards it.

## Remaining gaps

1. **Not on GitHub.** No credentials in this environment.
2. **Firefox/WebKit untested.** Wired but their bundles could not be fetched here.
3. **GitHub Actions never executed.** `ci_local.sh` passes all seven stages, which
   is the closest available proxy; expect environment-specific surprises anyway.
4. **No real Ollama.** The HTTP contract is verified against a faithful fake, but a
   real 14B model will produce messier output than a scripted responder. Prompt
   robustness is the thing most likely to need tuning on first contact.
5. **Rule grammar is English-only.** A floor, not a replacement for a model.
6. **`expect_json` compares by substring**, not type-aware equality. Fine for
   smoke assertions, insufficient for strict schema validation.
