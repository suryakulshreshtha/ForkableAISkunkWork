# Running with no network at all

## What "offline" means here

Three separate claims, each enforced rather than promised:

1. **No egress at run time.** `net_guard` patches `socket.connect`,
   `connect_ex`, `create_connection` and `getaddrinfo`. Anything that is not a
   loopback address raises `OfflineViolation` before a packet is sent, and DNS
   lookups for non-local names are refused so nothing leaks to a resolver.
2. **No cloud inference.** The only model endpoint is Ollama on
   `127.0.0.1:11434`, and the client refuses a non-loopback base URL outright.
3. **No network needed to be useful.** Without a model, planning falls back to a
   deterministic grammar and retrieval to a stdlib hashing embedder.

Verify all three:

```bash
python scripts/verify_offline.py
```

## The two things that do need a network, once

**Python packages.** Everything except Playwright is standard library, but
Playwright itself is a wheel.

**Browser binaries.** ~150 MB per engine, fetched from a CDN.

Both are handled by the bundle script, run on a connected machine:

```bash
./scripts/bootstrap_offline.sh forkable-offline-bundle
# copy forkable-offline-bundle.tar.gz across, then on the offline machine:
tar xzf forkable-offline-bundle.tar.gz
./scripts/bootstrap_offline.sh forkable-offline-bundle offline
```

That installs wheels with `--no-index --find-links`, and points
`PLAYWRIGHT_BROWSERS_PATH` at the copied bundle. Version-match the Playwright
wheel to the browser bundle or the driver refuses to start.

## Models

Copy `~/.ollama/models` from a machine that has already pulled them. The agent
resolves whatever is present:

```toml
model_preferences = ["qwen2.5-coder:14b", "qwen2.5-coder:7b", "qwen3:8b", "llama3.1:8b"]
```

If none are available, `forkable doctor` reports the daemon as unreachable and
the rule engine takes over. Plans stay correct; only phrasing flexibility and
failure-analysis prose are lost.

## Verifying in CI

The suite is split so that a build machine with no browser and no GPU still
covers the interesting logic:

```bash
pytest -m "not e2e"    # planning, healing, execution, codegen, RAG, reporting
pytest -m e2e          # real Chromium
```

The non-e2e suite drives a miniature DOM harness that speaks HTTP to the real
demo app, so healing is genuinely exercised rather than mocked.

## If something tries to phone home

You will see `OfflineViolation` with the refused host. Do not reach for
`--allow-network` first — find out what wanted out. Common culprits are
telemetry in a transitive dependency, a font CDN referenced by a page under
test, or a source-map fetch. An offline suite that quietly depends on the
internet is not an offline suite.
