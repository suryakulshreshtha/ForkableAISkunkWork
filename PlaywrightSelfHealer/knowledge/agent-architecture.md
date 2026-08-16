# PlaywrightSelfHealer architecture

## Pipeline

Natural language spec
→ **Planner** (local LLM, or the deterministic rule grammar)
→ validated **TestPlan** (semantic steps, no selectors)
→ **Executor** (resolves each step against the live DOM)
→ **LocatorResolver** (candidate ladder, then healing)
→ **RunResult** → **FailureAnalyzer** (rules + RAG) → **Report** (HTML + JSON)

Codegen branches off the validated plan: **TestGenerator** emits standalone
pytest + Playwright source, preferring locators the agent proved on a real page.

## Degradation ladder

Every component has a defined behaviour when its dependency is missing, because
"air-gapped" and "nothing installed yet" tend to arrive together.

| Missing | Behaviour |
| --- | --- |
| Ollama daemon | Rule grammar plans; heuristic scorer heals |
| Embedding model | Stdlib hashing embedder, still searchable |
| Pillow | Visual checks warn instead of failing the run |
| Browser bundle | Planning, codegen, RAG and reporting still work |
| Knowledge index | Analyzer falls back to its built-in rule table |

## Why healing is heuristic-first

The deterministic scorer runs before the model is consulted. It costs
microseconds, it is reproducible in CI, and on the common failure — an id churn
where the label survived — it is simply correct. The model is asked only when the
best heuristic score is weak, which keeps token spend near zero and means a dead
daemon degrades quality rather than breaking the run.

## Memory

Successful bindings are scored and persisted per `(page scope, description)`.
Later runs try proven locators first, and the generator emits them into standalone
tests. A healed selector therefore pays for itself twice: once at run time, once
in the generated code.

## Offline guarantee

`net_guard` patches `socket.connect`, `connect_ex`, `create_connection` and
`getaddrinfo`. Non-loopback addresses raise `OfflineViolation` before a packet
leaves the process, and DNS lookups for non-local names are refused outright.
Enforcement sits at the socket layer rather than in each client so it also covers
dependencies that were never asked to behave.
