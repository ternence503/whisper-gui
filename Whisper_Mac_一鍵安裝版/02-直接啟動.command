#!/bin/bash
cd "$(dirname "$0")"
chmod +x ./_internal/setup_and_run_mac.sh
./_internal/setup_and_run_mac.sh --only-launch
EXIT_CODE=$?
if [[ "$EXIT_CODE" -ne 0 ]]; then
  echo ""
  echo "啟動失敗，請先執行 01-一鍵安裝並啟動.command。"
  read -n 1 -s -r -p "按任意鍵關閉..."
  echo ""
fi
exit "$EXIT_CODE"
