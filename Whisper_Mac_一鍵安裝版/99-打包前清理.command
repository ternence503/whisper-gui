#!/bin/bash
# 打包前清理：移除本機環境、模型與 macOS 暫存檔
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INTERNAL="$DIR/_internal"

echo "開始清理..."

# 虛擬環境（安裝在使用者 Library，這裡的可刪）
if [[ -d "$INTERNAL/.venv" ]]; then
  echo "  移除 .venv ..."
  rm -rf "$INTERNAL/.venv"
fi

# Whisper 模型（安裝後存於 ~/Library/Application Support/WhisperGUI/models）
if [[ -d "$INTERNAL/models" ]]; then
  echo "  移除 models ..."
  rm -rf "$INTERNAL/models"
fi

# macOS 暫存 metadata（._* 與 .DS_Store）
echo "  移除 macOS 暫存檔 ..."
find "$DIR" -name "._*" -delete 2>/dev/null || true
find "$DIR" -name ".DS_Store" -delete 2>/dev/null || true

# Python cache
find "$DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

echo ""
echo "清理完成，可以打包了。"
read -n 1 -s -r -p "按任意鍵關閉..."
echo ""
