# ForkableAISkunkWork

Skunkworks projects exploring what local, offline AI agents can actually do —
no cloud APIs, no telemetry, no network.

## Projects

### [ForkableAIAgent](ForkableAIAgent/) — offline Playwright AI test agent

Turns plain English into Playwright tests, runs them, repairs the selectors your
app broke overnight, explains failures against a local knowledge base, and emits
standalone pytest code. Runs against a local Ollama model, or with no model at
all.

- **Stack:** Python 3.11+, Playwright, Ollama (`qwen2.5-coder`, `nomic-embed-text`), hybrid BM25 + dense RAG, stdlib everywhere else
- **Highlight:** the same spec passes before and after a UI refactor that deletes every `data-testid` and renames every id — the agent re-binds and remembers
- **Offline:** the socket layer is patched so non-loopback traffic and DNS both raise before a packet leaves the process
- **API + UI in one plan:** API steps run through the browser's cookie jar, so a UI login authenticates the API call that follows
- **Verified:** 125 tests, including real Chromium runs; two fake servers (a mini headless browser and an Ollama stand-in) keep coverage honest with no network and no GPU

```bash
cd ForkableAIAgent
pip install -e ".[dev,visual]"
python -m playwright install chromium
forkable doctor
forkable demo
```

See [ForkableAIAgent/README.md](ForkableAIAgent/README.md) for the full write-up,
and [RESULTS.md](ForkableAIAgent/RESULTS.md) for the verification table.

## Sibling repository

Companion to [ForkedUpAIExperiments](https://github.com/suryakulshreshtha/ForkedUpAIExperiments)
(local PDF RAG in Python, autonomous ADO code review agent in Go). Same
philosophy — enterprise-grade agents on consumer hardware, nothing leaving the
machine — and the same local model stack, so the two can share an Ollama install.

## Licence

MIT.
