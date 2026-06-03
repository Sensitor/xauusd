#!/usr/bin/env bash
# Idempotent dev environment bootstrap. Safe to run repeatedly; used by the
# SessionStart hook (Claude Code on the web) and by humans locally.
set -euo pipefail
cd "$(dirname "$0")/.."

# Skip the (potentially slow) install if the core is already importable.
if python3 -c "import pandas, pydantic, structlog, sqlalchemy, fastapi" >/dev/null 2>&1; then
  echo "goldmind: dependencies already present — skipping install."
else
  echo "goldmind: installing runtime + dev dependencies..."
  python3 -m pip install -q -r requirements.txt -r requirements-dev.txt || {
    echo "goldmind: pip install failed (offline?). Core tests may still run with cached deps." >&2
  }
fi

echo "goldmind: ready. Run 'PYTHONPATH=src python3 -m pytest -q' to verify."
