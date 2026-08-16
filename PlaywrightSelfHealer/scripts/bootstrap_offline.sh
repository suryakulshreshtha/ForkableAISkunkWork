#!/usr/bin/env bash
# Build a transfer bundle on a connected machine, then install from it on the
# air-gapped one. Run step 1 online, copy the folder, run step 2 offline.
set -euo pipefail

BUNDLE="${1:-forkable-offline-bundle}"

step_online() {
  echo "==> building $BUNDLE (needs network)"
  mkdir -p "$BUNDLE/wheelhouse"
  python3 -m pip download -r requirements-dev.txt -d "$BUNDLE/wheelhouse"

  echo "==> fetching the chromium bundle"
  PLAYWRIGHT_BROWSERS_PATH="$PWD/$BUNDLE/ms-playwright" python3 -m playwright install chromium

  echo "==> exporting local models (optional, large)"
  if command -v ollama >/dev/null 2>&1; then
    mkdir -p "$BUNDLE/ollama"
    echo "    copy ~/.ollama/models into $BUNDLE/ollama to move models across"
  fi

  tar czf "$BUNDLE.tar.gz" "$BUNDLE"
  echo "==> done: $BUNDLE.tar.gz - copy this to the offline machine"
}

step_offline() {
  echo "==> installing from $BUNDLE (no network required)"
  python3 -m pip install --no-index --find-links="$BUNDLE/wheelhouse" -e ".[dev,visual]"
  export PLAYWRIGHT_BROWSERS_PATH="$PWD/$BUNDLE/ms-playwright"
  echo "export PLAYWRIGHT_BROWSERS_PATH=$PWD/$BUNDLE/ms-playwright" >> ~/.bashrc
  PYTHONPATH=src python3 -m forkable_ai_agent index
  PYTHONPATH=src python3 -m forkable_ai_agent doctor
}

case "${2:-}" in
  offline) step_offline ;;
  *) if [ -d "$BUNDLE" ]; then step_offline; else step_online; fi ;;
esac
