#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${DIR}/../.." && pwd)"

# Resolve techfig executable (prefer repository virtual environment)
if [ -x "${REPO_DIR}/.venv/bin/techfig" ]; then
    TECHFIG="${REPO_DIR}/.venv/bin/techfig"
elif command -v techfig &> /dev/null; then
    TECHFIG="techfig"
else
    echo "Error: techfig executable not found in .venv or PATH" >&2
    exit 1
fi

echo "=== 1. Verifying model numerics ==="
"$TECHFIG" verify-model "${DIR}/spec.json"

echo "=== 2. Reconstructing static SVG diagram ==="
"$TECHFIG" reconstruct "${DIR}/spec.json" -o "${DIR}/diagram.svg"

echo "=== 3. Generating interactive widget HTML ==="
"$TECHFIG" interactive "${DIR}/spec.json" -o "${DIR}/widget.html"

echo "=== 4. Assembling standalone explainer HTML ==="
"$TECHFIG" explain "${DIR}/explainer.md" -o "${DIR}/explainer.html"

echo "=== 5. Running HTML critique ==="
"$TECHFIG" critique --html "${DIR}/widget.html" || {
    echo "Note: critique --html returned non-zero (e.g. playwright unavailable); continuing build."
}

echo "=== Build finished successfully ==="
