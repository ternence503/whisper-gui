#!/bin/bash
cd "$(dirname "$0")"
chmod +x ./setup_and_run_mac.sh
./setup_and_run_mac.sh "$@"
EXIT_CODE=$?
if [[ "$EXIT_CODE" -ne 0 ]]; then
  echo ""
  echo "安裝或啟動失敗，請把畫面截圖回傳。"
  read -n 1 -s -r -p "按任意鍵關閉..."
  echo ""
fi
exit "$EXIT_CODE"
