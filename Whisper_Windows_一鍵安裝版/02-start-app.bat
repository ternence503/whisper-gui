@echo off
setlocal

set SCRIPT_DIR=%~dp0
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%setup_and_run.ps1" -OnlyLaunch
set EXIT_CODE=%ERRORLEVEL%

if NOT "%EXIT_CODE%"=="0" (
  echo.
  echo 啟動失敗，請把上方訊息截圖後回傳。
  echo 若尚未安裝，請先執行 01-install-and-run.bat。
  pause
  exit /b %EXIT_CODE%
)

echo.
echo 程式已結束。按任意鍵關閉視窗。
pause
exit /b 0
