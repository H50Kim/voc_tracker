#!/usr/bin/env bash
# Record pytest output for CU-5 evidence (Linux CI or WSL).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PKG="$ROOT/computer_use"
OUT_DIR="${CU5_EVIDENCE_DIR:-$ROOT/evidence/pytest}"
MARKER="${1:-not-windows}"

mkdir -p "$OUT_DIR"
cd "$PKG"

case "$MARKER" in
  not-windows | not_windows)
    OUT="$OUT_DIR/pytest-not-windows.log"
    echo "Running: pytest -m \"not windows\" -> $OUT"
    pytest -m "not windows" 2>&1 | tee "$OUT"
    ;;
  windows)
    OUT="$OUT_DIR/pytest-windows.log"
    echo "Running: pytest -m windows -> $OUT"
    pytest -m windows 2>&1 | tee "$OUT"
    ;;
  full)
    OUT="$OUT_DIR/pytest-full.log"
    echo "Running: pytest -> $OUT"
    pytest 2>&1 | tee "$OUT"
    ;;
  *)
    echo "Usage: $0 [not-windows|windows|full]" >&2
    exit 2
    ;;
esac

echo "Saved: $OUT"
