#!/usr/bin/env bash
# Publish ForkableAISkunkWork to github.com/suryakulshreshtha, from macOS.
# See PUBLISHING.md for the annotated version of every step below.
set -euo pipefail

EMAIL="${GITHUB_EMAIL:-}"
OWNER="${OWNER:-suryakulshreshtha}"
REPO="${REPO:-ForkableAISkunkWork}"
DESC="Offline-first Playwright AI test agent: NL to tests, self-healing locators, local Ollama + RAG. No network required."

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PROJECT="$REPO_ROOT/ForkableAIAgent"

say()  { printf '\n\033[1m==> %s\033[0m\n' "$1"; }
die()  { printf '\033[31mERROR: %s\033[0m\n' "$1" >&2; exit 1; }

[ -n "$EMAIL" ] || die "set GITHUB_EMAIL to the address on your GitHub account.
GitHub attributes commits by email; without a match the history shows as an
unknown author. Find it at github.com/settings/emails."

command -v gh  >/dev/null || die "gh not found. brew install gh"
command -v git >/dev/null || die "git not found. brew install git"

say "Preflight: does CI pass locally?"
cd "$PROJECT"
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -e ".[dev,visual]"
python -m playwright install chromium
./scripts/ci_local.sh || die "CI would fail. Fix it before publishing - the
workflow cannot be tested once it is on GitHub, only observed failing."

say "Authorship"
cd "$REPO_ROOT"
git config user.name "Surya Kulshreshtha"
git config user.email "$EMAIL"
if git log -1 --pretty=format:'%ae' | grep -q 'forkable.local'; then
  echo "    rewriting placeholder author on all commits"
  git rebase -r --root --exec 'git commit --amend --no-edit --reset-author'
fi
git log --pretty=format:'    %h %an <%ae>' | head -3; echo

say "GitHub account"
gh auth status
gh auth status 2>&1 | grep -q "$OWNER" || die "gh is authenticated as a different
account. Run: gh auth switch"

say "Create and push"
if gh repo view "$OWNER/$REPO" >/dev/null 2>&1; then
  echo "    $OWNER/$REPO already exists; pushing to it"
  git remote set-url origin "https://github.com/$OWNER/$REPO.git" 2>/dev/null \
    || git remote add origin "https://github.com/$OWNER/$REPO.git"
  git push -u origin main
else
  gh repo create "$OWNER/$REPO" --public --source=. --remote=origin --push --description "$DESC"
fi

say "Topics"
gh repo edit "$OWNER/$REPO" \
  --add-topic playwright --add-topic ollama --add-topic ai-agent \
  --add-topic self-healing --add-topic offline-ai --add-topic rag \
  --add-topic python --add-topic test-automation

say "Done - https://github.com/$OWNER/$REPO"
echo "    watch the first CI run with: gh run watch"
