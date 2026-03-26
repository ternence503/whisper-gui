@echo off
chcp 65001 > nul
setlocal

set SCRIPT_DIR=%~dp0
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%setup_and_run.ps1" %*
set EXIT_CODE=%ERRORLEVEL%

if NOT "%EXIT_CODE%"=="0" (
  echo.
  echo 安裝或啟動失敗，請把上方訊息截圖後回傳。
  pause
  exit /b %EXIT_CODE%
)

echo.
echo 程式已結束。按任意鍵關閉視窗。
pause
exit /b 0
