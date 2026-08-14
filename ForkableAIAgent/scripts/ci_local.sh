#!/usr/bin/env bash
# Run the same steps as .github/workflows/ci.yml, locally.
# The workflow itself cannot be executed until the repo is pushed, so this is
# how you find out whether it will pass before it runs for real.
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH=src
FAIL=0

step() {
  printf '\n\033[1m==> %s\033[0m\n' "$1"; shift
  if "$@"; then printf '    \033[32mPASS\033[0m\n'; else printf '    \033[31mFAIL\033[0m\n'; FAIL=1; fi
}

step "Lint"                     python3 -m ruff check src tests scripts
step "Offline suite (no browser, no model)" env FORKABLE_OFFLINE=1 FORKABLE_LLM_PROVIDER=none \
                                   python3 -m pytest -m "not e2e" -q
step "Prove nothing escapes"    python3 scripts/verify_offline.py
step "Real browser suite"       python3 -m pytest -m e2e -q
step "Build the RAG index"      python3 -m forkable_ai_agent index
step "Generate a standalone test" python3 -m forkable_ai_agent generate \
                                   --file examples/nl_specs/login.txt --out tests/generated

printf '\n\033[1m==> Generated test runs standalone\033[0m\n'
python3 -m forkable_ai_agent serve >/dev/null 2>&1 &
SERVER=$!
trap 'kill $SERVER 2>/dev/null || true' EXIT
sleep 2
if python3 -m pytest tests/generated -o addopts="" --browser chromium -q; then
  printf '    \033[32mPASS\033[0m\n'
else
  printf '    \033[31mFAIL\033[0m\n'; FAIL=1
fi

printf '\n%s\n' "$([ $FAIL -eq 0 ] && echo 'CI would pass' || echo 'CI would FAIL')"
exit $FAIL
