#!/bin/bash
# SessionStart hook — prepares the environment so Claude Code (web) sessions can
# run the linter and tests immediately. Synchronous by design: dependencies are
# guaranteed installed before the agent starts.
set -euo pipefail

# Only run in the remote (Claude Code on the web) environment.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-.}"

# Best-effort pip upgrade; some base images ship a debian-managed pip that
# can't be uninstalled, so never let this abort the hook.
python -m pip install --quiet --upgrade pip || true

# --ignore-installed avoids a uninstall-RECORD conflict with the base image's
# debian-managed PyYAML. Falls back to a plain install if the flag is unhappy.
python -m pip install --quiet --ignore-installed -r requirements.txt \
  || python -m pip install --quiet -r requirements.txt

# Dev tooling for the status check (linter + test runner).
python -m pip install --quiet ruff pytest

# The app reads config.yaml at runtime; seed it from the example so smoke checks
# and manual runs work without hand-copying.
if [ ! -f config.yaml ]; then
  cp config.example.yaml config.yaml
fi

echo "session-start hook: dependencies + dev tools installed, config.yaml seeded."
