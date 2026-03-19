@echo off
setlocal

set SCRIPT_DIR=%~dp0
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%setup_and_run.ps1" %*
set EXIT_CODE=%ERRORLEVEL%

if NOT "%EXIT_CODE%"=="0" (
  echo.
  echo 安裝或啟動失敗，請把畫面截圖後回傳。
  pause
)

exit /b %EXIT_CODE%
