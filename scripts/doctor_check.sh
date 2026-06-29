#!/bin/bash
# Doctor check — one-command verification for busy operators
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

# Activate venv if present
if [ -d .venv ]; then
    source .venv/bin/activate 2>/dev/null || source .venv/Scripts/activate 2>/dev/null || true
fi

echo "=========================================="
echo "  DOCTOR CHECK — ultimate-trader-for-crypto"
echo "=========================================="

python -m production_replay.healthcheck
echo ""

echo "--- FOCUSED TESTS ---"
python -m pytest -q -k "quick_regime or replay_runner or accelerated or safety or launch" --tb=short

echo ""
echo "=========================================="
echo "  DOCTOR CHECK COMPLETE"
echo "=========================================="
