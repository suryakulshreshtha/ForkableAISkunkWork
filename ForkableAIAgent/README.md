# ForkableAIAgent

An offline-first Playwright test agent. It turns plain English into a test plan,
runs it against a live page, repairs selectors the app broke, explains failures
against a local knowledge base, and emits standalone pytest code — with a local
Ollama model, or with no model at all.

The design constraint that shaped everything: **it must work on a machine with
the network cable pulled out.** Not "works offline once warmed up" — the socket
layer is patched so a non-loopback connection raises before a packet leaves the
process.

```
$ forkable demo

=== v1: stable UI ===
PASSED login_happy_path  (0.3s)
  ok    1. goto          /login          http://127.0.0.1:8799/login
  ok    2. fill          username        testid([data-testid="username"])
  ok    3. fill          password        testid([data-testid="password"])
  ok    4. click         log in          testid([data-testid="login"])
  ok    5. expect_url    /dashboard      http://127.0.0.1:8799/dashboard
  ok    6. expect_text   Welcome

=== v2: refactored UI - ids and labels changed ===
PASSED login_happy_path  (0.5s)
  ok    1. goto          /login          http://127.0.0.1:8799/login
  ok    2. fill          username        css(#usr_1a2b) [healed]
  ok    3. fill          password        css(input[type="password"])
  ok    4. click         log in          role(button:log in)
  ok    5. expect_url    /dashboard      http://127.0.0.1:8799/dashboard
  ok    6. expect_text   Welcome
```

Same plan, same command. Between the two runs every `data-testid` was deleted,
every id was renamed and the labels were reworded. Nothing in the spec changed.

## Why the plan holds no selectors

A step carries `target: "username"`, never `#username`. Binding happens at run
time against the live DOM, through an ordered ladder:

```
data-testid → ARIA role + accessible name → label → placeholder → id/name → text → css path
```

If every rung misses, the healer takes a compact DOM snapshot and scores each
element against the description with a fuzzy token match — `password` still
matches `passphrase` on a shared prefix, `username` still matches `user name` on
substring. The winning selector is written to `.forkable/memory.json`, so the
next run tries it first and healing stays cold.

A local model is consulted **only** when the best heuristic score is weak. That
ordering is deliberate: the deterministic scorer is reproducible in CI, costs
microseconds, and on the common failure — an id churn where the label survived —
it is simply correct.

## Install

```bash
pip install -e ".[dev,visual]"
python -m playwright install chromium     # once, needs network
forkable doctor
```

Optional, for better plans and richer failure analysis:

```bash
ollama pull qwen2.5-coder:14b
ollama pull nomic-embed-text
forkable index
```

Without Ollama, everything still runs — a deterministic rule grammar plans and a
stdlib hashing embedder powers retrieval.

## Use

```bash
forkable doctor                  # offline readiness
forkable serve                   # bundled demo target on 127.0.0.1:8799
forkable index                   # build the local RAG index
forkable ask "why did my selector break?"

forkable plan "go to the login page, fill username with demo, click log in"
forkable run  --file examples/nl_specs/login.txt
forkable run  --file examples/nl_specs/login.txt --variant v2   # force healing
forkable generate --file examples/nl_specs/login.txt --show
forkable heal-report
forkable demo                    # both variants back to back
```

Every command takes `--allow-network` if you genuinely need to reach outside;
without it, the guard is armed.

## What the agent does

| Capability | How |
| --- | --- |
| Natural language → tests | Local LLM, or a deterministic regex grammar |
| Self-healing locators | Candidate ladder → fuzzy DOM scoring → optional LLM tie-break → persisted cache |
| AI-assisted generation | Plan → pytest + Playwright source, preferring locators proven on a real page |
| Failure analysis | Rule classification + hybrid RAG over local notes + optional LLM summary |
| Visual validation | Pillow pixel diff with tolerance, red-overlay heatmaps, baseline management |
| Cross-browser | Chromium, Firefox, WebKit via `--browser` |
| API + UI | Assertions poll the live page; the demo target exposes `/health` for API checks |
| Regression + CI | `pytest -m "not e2e"` needs no browser and no model |
| Context-aware execution | Locator memory is scoped per page path, so the same description can bind differently per page |

## Generated code improves after a run

Before the agent has seen the page it emits semantic locators derived from your
own words:

```python
page.get_by_role("textbox", name="username").fill("demo")
```

After a run it emits what actually bound:

```python
page.locator("[data-testid=\"username\"]").fill("demo")
```

Generated modules are parsed with `ast` and checked against an import and call
allowlist before being written. Model output is untrusted input and is treated
that way — `import subprocess`, `os.system`, `eval` and friends are rejected.

## Offline guarantee

`src/forkable_ai_agent/net_guard.py` patches `socket.connect`, `connect_ex`,
`create_connection` and `getaddrinfo`. Non-loopback addresses raise
`OfflineViolation`; DNS lookups for non-local names are refused outright.
Enforcement lives at the socket layer rather than in each client so it also
covers dependencies that were never asked to behave.

```bash
python scripts/verify_offline.py
```

```
outbound probes (all must be refused)
  ok    tcp to a public IP refused
  ok    dns lookup refused
  ok    tcp to a hostname refused
  ok    telemetry-style beacon refused
loopback must still work
  ok    demo target reachable on loopback
RESULT: PASS - nothing escaped
```

For a genuinely air-gapped machine, `scripts/bootstrap_offline.sh` builds a
transfer bundle (wheels + browser binaries) on a connected box and installs from
it with `--no-index` on the offline one.

## Degradation ladder

Nothing here hard-fails because a dependency is missing.

| Missing | Behaviour |
| --- | --- |
| Ollama daemon | Rule grammar plans; heuristic scorer heals |
| Embedding model | Stdlib hashing embedder; retrieval still works |
| Pillow | Visual checks warn instead of failing the run |
| Browser bundle | Planning, codegen, RAG and reporting still work |
| Knowledge index | Analyzer falls back to its built-in rule table |

## Testing

```bash
make test        # 96 tests, no browser and no model needed
make test-e2e    # real Chromium
```

The suite includes a miniature headless browser (`tests/support/fake_page.py`)
that speaks HTTP to the real demo app, parses the real HTML and implements the
slice of the Playwright page API the agent calls. It exists so that healing,
memory and execution stay covered on build machines where a 150 MB browser
download is not an option.

## Layout

```
src/forkable_ai_agent/
  net_guard.py        socket-level offline enforcement
  config.py           TOML + env settings
  schema.py           Step / TestPlan / RunResult / Diagnosis
  cli.py              argparse entry point
  llm/                ollama client, deterministic rule engine
  rag/                chunker, embeddings, BM25, vector store, retriever
  browser/            locator ladder, DOM snapshot, Playwright session
  agent/              planner, healer, executor, generator, analyzer, memory
  visual/             baseline management and pixel diffing
  reporting/          self-contained HTML + JSON reports
  testapp/            the offline demo target with its v2 refactor variant
knowledge/            the corpus the RAG layer retrieves from
tests/                unit, integration and e2e suites
```

## Relationship to ForkedUpAIExperiments

Built to sit alongside
[ForkedUpAIExperiments](https://github.com/suryakulshreshtha/ForkedUpAIExperiments),
and it reuses that stack's assumptions: Ollama on loopback, `qwen2.5-coder` for
generation, `nomic-embed-text` for embeddings. If a configured model is not
pulled, the client resolves against `ollama list` and picks the best available,
so a shared box needs no extra downloads.

The one deliberate divergence is the vector store. That project uses ChromaDB;
this one defaults to a JSONL store with a cosine scan, because a corpus of a few
hundred engineering notes does not justify a dependency tree that is painful to
mirror onto an air-gapped machine. If you want them to share a store, install
the extra and set `backend = "chroma"` in `config/agent.toml` —
`rag/chroma_store.py` is a drop-in with telemetry disabled.

## Known nuances

- Locator memory is scoped by URL path. The demo's two variants share `/login`,
  so after running both, the generator emits whichever locator scored highest
  most recently. Real apps do not serve two DOMs at one path; if yours does,
  scope the memory file per environment.
- Font rendering differs between machines, so visual baselines should be
  produced in the same container that verifies them.
- The healer repairing a selector is a bug report against the app. The durable
  fix is adding a `data-testid`, not letting the agent guess forever.
