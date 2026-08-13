#!/usr/bin/env bash
# Publish this repository. Run from the repo root (the folder containing
# ForkableAIAgent/). Requires the GitHub CLI, or edit REMOTE and use plain git.
set -euo pipefail

OWNER="${OWNER:-suryakulshreshtha}"
REPO="${REPO:-ForkableAISkunkWork}"
REMOTE="git@github.com:${OWNER}/${REPO}.git"

if ! git rev-parse --git-dir >/dev/null 2>&1; then
  git init -b main
  git add -A
  git commit -m "ForkableAIAgent: offline Playwright AI agent"
fi

if command -v gh >/dev/null 2>&1; then
  gh repo create "${OWNER}/${REPO}" --public --source=. --remote=origin --push
else
  echo "gh not found - create ${REPO} on github.com, then:"
  git remote add origin "$REMOTE" 2>/dev/null || git remote set-url origin "$REMOTE"
  git push -u origin main
fi
