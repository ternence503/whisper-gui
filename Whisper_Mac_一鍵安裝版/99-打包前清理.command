#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Developer tool: pre-release cleanup
echo "[Developer tool] Pre-release cleanup"
echo "This removes .venv, models, and caches."
echo ""
read -r -p "Confirm cleanup (y/N)? " CONFIRM

if [[ "${CONFIRM:-}" != "y" && "${CONFIRM:-}" != "Y" ]]; then
  echo "Cancelled."
  exit 0
fi

echo "[1/4] Removing .venv..."
rm -rf "$SCRIPT_DIR/_internal/.venv"

echo "[2/4] Removing models..."
if [[ -d "$SCRIPT_DIR/_internal/models" ]]; then
  find "$SCRIPT_DIR/_internal/models" -mindepth 1 ! -name ".gitkeep" -exec rm -rf {} +
fi

echo "[3/4] Removing Python cache..."
find "$SCRIPT_DIR" -type d -name "__pycache__" -prune -exec rm -rf {} +
find "$SCRIPT_DIR" -type f -name "*.pyc" -delete

echo "[4/4] Removing macOS temp files..."
find "$SCRIPT_DIR" -type f -name ".DS_Store" -delete
find "$SCRIPT_DIR" -type f -name "._*" -delete

echo "Done. Ready to zip and distribute."
read -n 1 -s -r -p "Press any key to close..."
echo ""
