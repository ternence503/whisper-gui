#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "將清理以下內容："
echo "- .venv (Python 虛擬環境)"
echo "- models 內已下載模型（保留 .gitkeep）"
echo "- __pycache__ / *.pyc"
echo "- .DS_Store / ._*"
echo ""
read -r -p "確認清理（y/N）？ " CONFIRM

if [[ "${CONFIRM:-}" != "y" && "${CONFIRM:-}" != "Y" ]]; then
  echo "已取消。"
  exit 0
fi

echo "[1/5] 清理虛擬環境..."
rm -rf "$SCRIPT_DIR/.venv"

echo "[2/5] 清理模型檔..."
if [[ -d "$SCRIPT_DIR/models" ]]; then
  find "$SCRIPT_DIR/models" -mindepth 1 ! -name ".gitkeep" -exec rm -rf {} +
fi

echo "[3/5] 清理 Python 快取..."
find "$SCRIPT_DIR" -type d -name "__pycache__" -prune -exec rm -rf {} +
find "$SCRIPT_DIR" -type f -name "*.pyc" -delete

echo "[4/5] 清理 macOS 暫存..."
find "$SCRIPT_DIR" -type f -name ".DS_Store" -delete
find "$SCRIPT_DIR" -type f -name "._*" -delete

echo "[5/5] 完成"
echo "現在可以直接壓縮整個資料夾給新手。"
read -n 1 -s -r -p "按任意鍵關閉..."
echo ""
